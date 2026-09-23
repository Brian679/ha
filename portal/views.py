from datetime import timedelta
from decimal import Decimal
from io import BytesIO
import os
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from .decorators import ACADEMIC_STAFF_ROLES, STAFF_ROLES, roles_required
from .forms import (
    AnnouncementForm, AssignmentForm, AssessmentForm, AttendanceForm, ClassForm,
    EventForm, InvoiceForm, MaterialForm, MessageForm, PaymentForm, PortalLoginForm,
    AdmissionApplicationForm, ProfileForm, StudentForm, StudentProfileForm, SubjectForm, SubmissionForm, TeacherForm,
    TimetableSlotForm,
)
from .models import (
    AcademicYear, Announcement, Assignment, AssignmentSubmission, Assessment, Attendance,
    AdmissionApplication, AuditLog, Event, FeeStructure, Form, Invoice, LearningMaterial, Mark, Message,
    Notification, Parent, Payment, School, SchoolClass, Student, Subject, Teacher,
    TeachingAssignment, Term, TimetableSlot, User,
)


ADMIN_ROLES = (User.Role.ADMIN, User.Role.PRINCIPAL)
FINANCE_ROLES = (User.Role.ADMIN, User.Role.PRINCIPAL, User.Role.BURSAR)


def school_for(request):
    if not request.user.school:
        raise Http404("This account is not attached to a school.")
    return request.user.school


def audit(request, action, instance=None, detail=""):
    school = request.user.school
    if not school:
        return
    AuditLog.objects.create(
        school=school, user=request.user, action=action,
        record_type=instance.__class__.__name__ if instance else "System",
        record_id=str(instance.pk) if instance and instance.pk else "",
        detail=detail, ip_address=request.META.get("REMOTE_ADDR") or None,
    )


def paginate(request, queryset, per_page=12):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def visible_announcements(user):
    if user.role in (User.Role.ADMIN, User.Role.PRINCIPAL, User.Role.BURSAR):
        return Announcement.objects.filter(school=user.school)
    qs = Announcement.objects.filter(school=user.school).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
    allowed = Q(audience="EVERYONE")
    if user.role == User.Role.TEACHER: allowed |= Q(audience="TEACHERS")
    if user.role == User.Role.PARENT: allowed |= Q(audience="PARENTS")
    if user.role == User.Role.STUDENT:
        allowed |= Q(audience="STUDENTS")
        try:
            classes = user.student_profile.enrollments.filter(is_active=True).values_list("school_class", flat=True)
            forms = user.student_profile.enrollments.filter(is_active=True).values_list("school_class__form", flat=True)
            allowed |= Q(audience="CLASS", school_class_id__in=classes) | Q(audience="FORM", form_id__in=forms)
        except Student.DoesNotExist:
            pass
    return qs.filter(allowed)


class PortalLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = PortalLoginForm

    def form_valid(self, form):
        user = form.get_user()
        if user.school and not user.school.is_active:
            form.add_error(None, "This school account is currently inactive.")
            return self.form_invalid(form)
        return super().form_valid(form)


def home(request):
    return render(request, "public/home.html", {"school_count": School.objects.filter(is_active=True).count() or 28})


def admission_apply(request):
    school_slug = request.GET.get("school") or request.POST.get("school") or "higher-achievers"
    school = School.objects.filter(slug=school_slug, is_active=True).first() or School.objects.filter(is_active=True).order_by("created_at", "pk").first()
    if not school:
        return render(request, "public/admission_apply.html", {"form": None, "school": None})
    form = AdmissionApplicationForm(request.POST or None, request.FILES or None, school=school)
    application = None
    if request.method == "POST" and form.is_valid():
        application = form.save(commit=False)
        application.school = school
        if not application.application_number:
            application.application_number = f"ADM-{timezone.now():%Y}-{AdmissionApplication.objects.filter(school=school).count() + 1:04d}"
        password = form.cleaned_data.get("password1")
        if password:
            with transaction.atomic():
                application.save()
                email = application.email.lower()
                if not User.objects.filter(email=email).exists():
                    user = User.objects.create_user(
                        username=f"applicant-{school.slug}-{application.application_number}"[:150],
                        email=email,
                        first_name=application.first_name,
                        last_name=application.last_name,
                        phone=application.phone,
                        school=school,
                        role=User.Role.STUDENT,
                        password=password,
                        must_change_password=False,
                        email_verified=False,
                    )
                    application.user = user
                    application.save(update_fields=["user"])
        else:
            application.save()
        messages.success(request, "Your application has been submitted. Higher Achievers will contact you after review.")
        return render(request, "public/admission_apply.html", {"form": None, "school": school, "application": application})
    return render(request, "public/admission_apply.html", {"form": form, "school": school, "application": application})


def admission_track(request):
    application = None
    error = None
    if request.method == "POST":
        application_number = request.POST.get("application_number", "").strip()
        email = request.POST.get("email", "").strip().lower()
        if not application_number or not email:
            error = "Please provide both your application number and email."
        else:
            application = AdmissionApplication.objects.filter(application_number=application_number, email=email, school__is_active=True).select_related("school").first()
            if not application:
                error = "No application found with those details. Please check and try again."
    return render(request, "public/admission_track.html", {"application": application, "error": error})


@login_required
def my_application_status(request):
    school = request.user.school
    applications = AdmissionApplication.objects.filter(school=school, email=request.user.email).select_related("desired_class__form", "desired_class__academic_year").order_by("-created_at")
    return render(request, "portal/my_application_status.html", {"applications": applications})


@roles_required(*ADMIN_ROLES)
def admissions(request):
    school = school_for(request)
    status = request.GET.get("status", AdmissionApplication.Status.PENDING)
    applications = AdmissionApplication.objects.filter(school=school).select_related("desired_class__form", "desired_class__academic_year")
    if status in AdmissionApplication.Status.values:
        applications = applications.filter(status=status)
    return render(request, "portal/admissions.html", {"applications": applications, "status": status, "statuses": AdmissionApplication.Status.choices})


@roles_required(*ADMIN_ROLES)
def admission_detail(request, pk):
    school = school_for(request)
    application = get_object_or_404(AdmissionApplication.objects.select_related("desired_class__form", "desired_class__academic_year", "approved_by", "student__user"), pk=pk, school=school)
    return render(request, "portal/admission_detail.html", {"application": application})


@roles_required(*ADMIN_ROLES)
@require_POST
def admission_approve(request, pk):
    school = school_for(request)
    application = get_object_or_404(AdmissionApplication, pk=pk, school=school, status=AdmissionApplication.Status.PENDING)
    with transaction.atomic():
        email = application.email.lower()
        existing_user = User.objects.filter(email=email).first()
        if existing_user and Student.objects.filter(user=existing_user, school=school).exists():
            messages.error(request, "A student account already exists with this applicant email.")
            return redirect("admissions")
        if existing_user:
            user = existing_user
            student_number = f"HA-{timezone.now():%Y}-{Student.objects.filter(school=school).count() + 1:04d}"
        else:
            student_number = f"HA-{timezone.now():%Y}-{Student.objects.filter(school=school).count() + 1:04d}"
            user = User.objects.create_user(
                username=f"student-{school.slug}-{student_number}"[:150], email=email,
                first_name=application.first_name, last_name=application.last_name,
                phone=application.phone, school=school, role=User.Role.STUDENT,
                password="ChangeMe2026!", must_change_password=True, email_verified=False,
            )
        student = Student.objects.create(
            school=school, user=user, student_number=student_number,
            admission_number=f"ADM-{timezone.now():%Y}-{student_number[-4:]}",
            first_name=application.first_name, last_name=application.last_name,
            date_of_birth=application.date_of_birth, gender=application.gender or "OTHER",
            address=application.address, emergency_contact=application.phone,
        )
        application.status = AdmissionApplication.Status.APPROVED
        application.student = student
        application.approved_by = request.user
        application.approved_at = timezone.now()
        application.save(update_fields=["status", "student", "approved_by", "approved_at"])
        audit(request, "Approved admission application", application, f"Created student account for {student}")
    messages.success(request, f"{student} was approved. Temporary password: ChangeMe2026!.")
    return redirect("admissions")


@roles_required(*ADMIN_ROLES)
@require_POST
def admission_reject(request, pk):
    application = get_object_or_404(AdmissionApplication, pk=pk, school=school_for(request), status=AdmissionApplication.Status.PENDING)
    application.status = AdmissionApplication.Status.REJECTED
    application.approved_by = request.user
    application.approved_at = timezone.now()
    application.save(update_fields=["status", "approved_by", "approved_at"])
    audit(request, "Rejected admission application", application)
    messages.success(request, "Admission application rejected.")
    return redirect("admissions")


@login_required
def dashboard(request):
    if request.user.is_superuser and not request.user.school:
        return redirect("admin:index")
    if not request.user.school:
        return render(request, "portal/no_school.html", {"title": "Account setup required"}, status=403)
    role = request.user.role
    if role == User.Role.SUPER_ADMIN:
        return super_dashboard(request)
    if role in ADMIN_ROLES:
        return admin_dashboard(request)
    if role == User.Role.TEACHER:
        if not Teacher.objects.filter(user=request.user, school=request.user.school).exists():
            return render(request, "portal/profile_setup.html", {"account_type": "teacher"}, status=403)
        return teacher_dashboard(request)
    if role == User.Role.STUDENT:
        student_exists = Student.objects.filter(user=request.user, school=request.user.school).exists()
        if not student_exists:
            has_application = AdmissionApplication.objects.filter(school=request.user.school, email=request.user.email).exists()
            if has_application:
                return my_application_status(request)
            return render(request, "portal/profile_setup.html", {"account_type": "student"}, status=403)
        return student_dashboard(request)
    if role == User.Role.PARENT:
        if not Parent.objects.filter(user=request.user, school=request.user.school).exists():
            return render(request, "portal/profile_setup.html", {"account_type": "parent"}, status=403)
        return parent_dashboard(request)
    if role == User.Role.BURSAR:
        return bursar_dashboard(request)
    return render(request, "portal/empty.html", {"title": "Dashboard", "message": "Your role has not been configured yet."})


@roles_required(User.Role.SUPER_ADMIN)
def super_dashboard(request):
    schools = School.objects.annotate(student_count=Count("student"), user_count=Count("users", distinct=True))
    return render(request, "portal/super_dashboard.html", {"schools": schools[:8], "school_count": schools.count(), "student_count": Student.objects.count(), "user_count": User.objects.count(), "recent_schools": schools.order_by("-created_at")[:6]})


@roles_required(*ADMIN_ROLES)
def admin_dashboard(request):
    school = school_for(request)
    today = timezone.localdate()
    students = Student.objects.filter(school=school, is_active=True)
    attendance = Attendance.objects.filter(school=school, date=today)
    invoices = Invoice.objects.filter(school=school)
    paid_amount = Payment.objects.filter(school=school).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    invoiced = invoices.exclude(status=Invoice.Status.VOID).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    attendance_total = attendance.count()
    attendance_present = attendance.filter(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.EXCUSED]).count()
    chart_forms = list(students.values("enrollments__school_class__form__name").annotate(count=Count("id", distinct=True)).order_by("enrollments__school_class__form__level"))
    performance = Mark.objects.filter(school=school).values("assessment__school_class__name").annotate(average=Avg("obtained_mark")).order_by("assessment__school_class__name")[:6]
    context = {
        "total_students": students.count(), "total_teachers": Teacher.objects.filter(school=school, is_active=True).count(),
        "total_classes": SchoolClass.objects.filter(school=school).count(), "total_subjects": Subject.objects.filter(school=school, is_active=True).count(),
        "attendance_pct": round(100 * attendance_present / attendance_total, 1) if attendance_total else 0,
        "attendance_present": attendance_present, "attendance_total": attendance_total,
        "outstanding_fees": invoiced - paid_amount, "fees_collected": paid_amount,
        "upcoming_exams": Assessment.objects.filter(school=school, date__gte=today).count(),
        "pending_assignments": Assignment.objects.filter(school=school, due_date__gte=timezone.now()).count(),
        "announcements": Announcement.objects.filter(school=school)[:5], "activities": AuditLog.objects.filter(school=school)[:8],
        "form_chart": chart_forms, "performance": performance,
        "applications": AdmissionApplication.objects.filter(school=school).order_by("-created_at")[:5],
    }
    return render(request, "portal/admin_dashboard.html", context)


@roles_required(User.Role.TEACHER)
def teacher_dashboard(request):
    school = school_for(request); teacher = get_object_or_404(Teacher, user=request.user, school=school)
    today = timezone.localdate()
    assignments = TeachingAssignment.objects.filter(teacher=teacher).select_related("school_class", "subject")
    classes = SchoolClass.objects.filter(teaching_assignments__teacher=teacher).distinct()
    return render(request, "portal/teacher_dashboard.html", {
        "teacher": teacher, "assignments": assignments, "classes": classes,
        "today_slots": TimetableSlot.objects.filter(teacher=teacher, day=today.isoweekday()).select_related("subject", "school_class"),
        "pending_marks": Assessment.objects.filter(teacher=teacher, marks__isnull=True).distinct().count(),
        "upcoming_assignments": Assignment.objects.filter(teacher=teacher, due_date__gte=timezone.now())[:5],
        "announcements": visible_announcements(request.user)[:5],
        "messages": Message.objects.filter(recipient=request.user)[:5],
    })


@roles_required(User.Role.STUDENT)
def student_dashboard(request):
    school = school_for(request); student = get_object_or_404(Student, user=request.user, school=school)
    enrollment = student.enrollments.filter(is_active=True).select_related("school_class").first()
    current_class = enrollment.school_class if enrollment else None
    today = timezone.localdate()
    attendance_qs = student.attendance_records.all()
    total = attendance_qs.count(); present = attendance_qs.filter(status__in=["PRESENT", "LATE", "EXCUSED"]).count()
    return render(request, "portal/student_dashboard.html", {
        "student": student, "current_class": current_class,
        "today_slots": TimetableSlot.objects.filter(school_class=current_class, day=today.isoweekday()).select_related("subject", "teacher") if current_class else [],
        "assignments": Assignment.objects.filter(school_class=current_class, published=True, due_date__gte=timezone.now())[:5] if current_class else [],
        "attendance_pct": round(100 * present / total, 1) if total else 0,
        "fee_balance": student_balance(student), "announcements": visible_announcements(request.user)[:5],
        "results": Mark.objects.filter(student=student, assessment__published=True).select_related("assessment", "assessment__subject")[:6],
    })


@roles_required(User.Role.PARENT)
def parent_dashboard(request):
    school = school_for(request); parent = get_object_or_404(Parent, user=request.user, school=school)
    children = parent.children.filter(is_active=True).prefetch_related("enrollments__school_class")
    child_cards = []
    for child in children:
        total = child.attendance_records.count(); good = child.attendance_records.filter(status__in=["PRESENT", "LATE", "EXCUSED"]).count()
        child_cards.append({"student": child, "attendance": round(good * 100 / total, 1) if total else 0, "balance": student_balance(child), "class": child.enrollments.filter(is_active=True).first()})
    return render(request, "portal/parent_dashboard.html", {"parent": parent, "child_cards": child_cards, "announcements": visible_announcements(request.user)[:5]})


@roles_required(User.Role.BURSAR)
def bursar_dashboard(request):
    school = school_for(request)
    invoiced = Invoice.objects.filter(school=school).exclude(status=Invoice.Status.VOID).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    collected = Payment.objects.filter(school=school).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return render(request, "portal/bursar_dashboard.html", {"invoiced": invoiced, "collected": collected, "outstanding": invoiced-collected, "open_invoices": Invoice.objects.filter(school=school).exclude(status=Invoice.Status.PAID).count(), "recent_payments": Payment.objects.filter(school=school).select_related("invoice", "invoice__student")[:8], "invoices": Invoice.objects.filter(school=school).select_related("student")[:6]})


def student_balance(student):
    invoices = student.invoices.exclude(status=Invoice.Status.VOID)
    total = invoices.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    paid = Payment.objects.filter(invoice__in=invoices).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return total - paid


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def students(request):
    school = school_for(request); query = request.GET.get("q", "").strip(); class_id = request.GET.get("class")
    qs = Student.objects.filter(school=school).prefetch_related("enrollments__school_class", "parents__user")
    if request.user.role == User.Role.TEACHER:
        teacher = get_object_or_404(Teacher, user=request.user, school=school)
        teacher_classes = SchoolClass.objects.filter(Q(teaching_assignments__teacher=teacher) | Q(class_teacher=teacher)).distinct()
        qs = qs.filter(enrollments__school_class__in=teacher_classes, enrollments__is_active=True).distinct()
        classes = teacher_classes
    else:
        classes = SchoolClass.objects.filter(school=school)
    if query: qs = qs.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(student_number__icontains=query) | Q(admission_number__icontains=query))
    if class_id: qs = qs.filter(enrollments__school_class_id=class_id, enrollments__is_active=True)
    return render(request, "portal/students.html", {"students": paginate(request, qs), "q": query, "classes": classes, "selected_class": class_id})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def student_create(request):
    school = school_for(request)
    teacher = Teacher.objects.filter(user=request.user, school=school).first() if request.user.role == User.Role.TEACHER else None
    form = StudentForm(request.POST or None, request.FILES or None, school=school, teacher=teacher)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data.get("email", "").strip().lower()
        password = form.cleaned_data.get("password") or "ChangeMe2026!"
        school_class = form.cleaned_data.get("school_class")
        if Student.objects.filter(school=school, student_number=form.cleaned_data["student_number"]).exists():
            form.add_error("student_number", "This student number is already in use at this school.")
        elif email and User.objects.filter(email=email).exists():
            form.add_error("email", "An account with this email already exists.")
        else:
            with transaction.atomic():
                student = form.save(commit=False)
                student.school = school
                student.save()
                if email:
                    user = User.objects.create_user(username=f"student-{school.slug}-{student.student_number}"[:150], email=email, first_name=student.first_name, last_name=student.last_name, school=school, role=User.Role.STUDENT, password=password, must_change_password=not bool(form.cleaned_data.get("password")))
                    student.user = user
                    student.save(update_fields=["user"])
                if school_class:
                    student.enrollments.create(school=school, school_class=school_class, academic_year=school_class.academic_year)
                audit(request, "Created student", student)
            messages.success(request, f"{student} was added successfully." + (f" Temporary password: {password}." if email and not form.cleaned_data.get("password") else ""))
            return redirect("student_detail", pk=student.pk)
    return render(request, "portal/form_page.html", {"form": form, "title": "Add student", "back_url": "students", "submit_label": "Create student"})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def student_detail(request, pk):
    school = school_for(request)
    student_qs = Student.objects.prefetch_related("parents__user", "enrollments__school_class", "attendance_records", "marks__assessment__subject", "invoices").filter(school=school)
    if request.user.role == User.Role.TEACHER:
        teacher = get_object_or_404(Teacher, user=request.user, school=school)
        teacher_classes = SchoolClass.objects.filter(Q(teaching_assignments__teacher=teacher) | Q(class_teacher=teacher)).distinct()
        student_qs = student_qs.filter(enrollments__school_class__in=teacher_classes, enrollments__is_active=True).distinct()
    student = get_object_or_404(student_qs, pk=pk)
    active_classes = SchoolClass.objects.filter(school=school)
    if request.user.role == User.Role.TEACHER:
        active_classes = active_classes.filter(Q(teaching_assignments__teacher=teacher) | Q(class_teacher=teacher)).distinct()
    if request.method == "POST" and request.POST.get("action") == "enrol":
        class_id = request.POST.get("school_class")
        school_class = get_object_or_404(active_classes, pk=class_id)
        academic_year = school_class.academic_year
        student.enrollments.update(is_active=False)
        enrollment, _ = student.enrollments.get_or_create(school=school, school_class=school_class, academic_year=academic_year, defaults={"is_active": True})
        if not enrollment.is_active: enrollment.is_active = True; enrollment.save(update_fields=["is_active"])
        audit(request, "Enrolled student", student, f"Assigned to {school_class}")
        messages.success(request, f"{student} is now enrolled in {school_class}.")
        return redirect("student_detail", pk=pk)
    marks = student.marks.filter(assessment__published=True).select_related("assessment", "assessment__subject")[:12]
    return render(request, "portal/student_detail.html", {"student": student, "classes": active_classes, "marks": marks, "balance": student_balance(student)})


@roles_required(*ADMIN_ROLES)
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk, school=school_for(request)); form = StudentForm(request.POST or None, request.FILES or None, instance=student)
    if request.method == "POST" and form.is_valid(): form.save(); audit(request, "Updated student", student); messages.success(request, "Student record saved."); return redirect("student_detail", pk=pk)
    return render(request, "portal/form_page.html", {"form": form, "title": f"Edit {student}", "back_url": "student_detail", "back_args": [pk], "submit_label": "Save changes"})


@roles_required(*ADMIN_ROLES)
@require_POST
def student_toggle(request, pk):
    student = get_object_or_404(Student, pk=pk, school=school_for(request)); student.is_active = not student.is_active; student.save(update_fields=["is_active"]); audit(request, "Changed student activation", student); messages.success(request, "Student status updated."); return redirect("students")


@roles_required(*ADMIN_ROLES)
def teachers(request):
    school = school_for(request); query = request.GET.get("q", "")
    qs = Teacher.objects.filter(school=school).select_related("user").prefetch_related("teaching_assignments__school_class", "teaching_assignments__subject").order_by("user__last_name", "user__first_name")
    if query: qs = qs.filter(Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(employee_number__icontains=query) | Q(user__email__icontains=query))
    return render(request, "portal/teachers.html", {"teachers": paginate(request, qs), "q": query})


@roles_required(*ADMIN_ROLES)
def teacher_create(request):
    school = school_for(request); form = TeacherForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            email = form.cleaned_data["email"].lower()
            if User.objects.filter(email=email).exists(): form.add_error("email", "An account with this email already exists.")
            elif Teacher.objects.filter(school=school, employee_number=form.cleaned_data["employee_number"]).exists(): form.add_error("employee_number", "This employee number is already in use.")
            else:
                username = f"teacher-{school.slug}-{form.cleaned_data['employee_number']}"[:150]
                user = User.objects.create_user(username=username, email=email, first_name=form.cleaned_data["first_name"], last_name=form.cleaned_data["last_name"], phone=form.cleaned_data["phone"], school=school, role=User.Role.TEACHER, password="ChangeMe2026!", must_change_password=True, is_active=form.cleaned_data["is_active"])
                teacher = Teacher.objects.create(school=school, user=user, employee_number=form.cleaned_data["employee_number"], qualification=form.cleaned_data["qualification"], department=form.cleaned_data["department"], is_active=form.cleaned_data["is_active"])
                audit(request, "Created teacher", teacher); messages.success(request, "Teacher created. Their temporary password is set to ChangeMe2026!."); return redirect("teacher_detail", pk=teacher.pk)
    return render(request, "portal/form_page.html", {"form": form, "title": "Add teacher", "back_url": "teachers", "submit_label": "Create teacher"})


@roles_required(*ADMIN_ROLES)
def teacher_detail(request, pk):
    school = school_for(request); teacher = get_object_or_404(Teacher.objects.select_related("user"), pk=pk, school=school)
    if request.method == "POST" and request.POST.get("action") == "assign":
        school_class = get_object_or_404(SchoolClass, pk=request.POST.get("school_class"), school=school)
        subject = get_object_or_404(Subject, pk=request.POST.get("subject"), school=school)
        TeachingAssignment.objects.get_or_create(school=school, teacher=teacher, school_class=school_class, subject=subject)
        audit(request, "Assigned teacher", teacher, f"{subject} to {school_class}"); messages.success(request, "Teaching allocation saved."); return redirect("teacher_detail", pk=pk)
    return render(request, "portal/teacher_detail.html", {"teacher": teacher, "allocations": teacher.teaching_assignments.select_related("school_class", "subject"), "classes": SchoolClass.objects.filter(school=school), "subjects": Subject.objects.filter(school=school, is_active=True), "timetable": TimetableSlot.objects.filter(teacher=teacher).select_related("school_class", "subject")})


@roles_required(*ADMIN_ROLES)
def teacher_edit(request, pk):
    school = school_for(request); teacher = get_object_or_404(Teacher, pk=pk, school=school); form = TeacherForm(request.POST or None, teacher=teacher)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data; user = teacher.user
        if User.objects.exclude(pk=user.pk).filter(email=data["email"].lower()).exists(): form.add_error("email", "An account with this email already exists.")
        else:
            user.first_name, user.last_name, user.email, user.phone, user.is_active = data["first_name"], data["last_name"], data["email"].lower(), data["phone"], data["is_active"]; user.save()
            teacher.employee_number, teacher.qualification, teacher.department, teacher.is_active = data["employee_number"], data["qualification"], data["department"], data["is_active"]; teacher.save(); audit(request, "Updated teacher", teacher); messages.success(request, "Teacher record saved."); return redirect("teacher_detail", pk=pk)
    return render(request, "portal/form_page.html", {"form": form, "title": f"Edit {teacher}", "back_url": "teacher_detail", "back_args": [pk], "submit_label": "Save changes"})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def classes(request):
    school = school_for(request)
    qs = SchoolClass.objects.filter(school=school).select_related("form", "academic_year", "class_teacher__user").annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
    if request.user.role == User.Role.TEACHER:
        teacher = get_object_or_404(Teacher, user=request.user, school=school)
        qs = qs.filter(Q(teaching_assignments__teacher=teacher) | Q(class_teacher=teacher)).distinct()
    return render(request, "portal/classes.html", {"classes": qs, "form_count": Form.objects.filter(school=school).count()})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def class_create(request):
    school = school_for(request); teacher = Teacher.objects.filter(user=request.user, school=school).first() if request.user.role == User.Role.TEACHER else None; form = ClassForm(request.POST or None, school=school, teacher=teacher)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school
        if teacher:
            obj.class_teacher = teacher
        obj.save(); audit(request, "Created class", obj); messages.success(request, "Class created."); return redirect("classes")
    return render(request, "portal/form_page.html", {"form": form, "title": "Create class", "back_url": "classes", "submit_label": "Create class"})


@roles_required(*ADMIN_ROLES)
def subjects(request):
    school = school_for(request); query = request.GET.get("q", ""); qs = Subject.objects.filter(school=school)
    if query: qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
    return render(request, "portal/subjects.html", {"subjects": qs, "q": query})


@roles_required(*ADMIN_ROLES)
def subject_create(request):
    school = school_for(request); form = SubjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school; obj.save(); audit(request, "Created subject", obj); messages.success(request, "Subject added."); return redirect("subjects")
    return render(request, "portal/form_page.html", {"form": form, "title": "Add subject", "back_url": "subjects", "submit_label": "Add subject"})


@roles_required(*ADMIN_ROLES)
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk, school=school_for(request)); form = SubjectForm(request.POST or None, instance=subject)
    if request.method == "POST" and form.is_valid(): form.save(); audit(request, "Updated subject", subject); messages.success(request, "Subject saved."); return redirect("subjects")
    return render(request, "portal/form_page.html", {"form": form, "title": f"Edit {subject.name}", "back_url": "subjects", "submit_label": "Save changes"})


@roles_required(*ACADEMIC_STAFF_ROLES)
def attendance(request):
    school = school_for(request); user = request.user; selected = request.GET.get("class") or request.POST.get("school_class"); date = request.GET.get("date") or request.POST.get("date") or str(timezone.localdate())
    class_qs = SchoolClass.objects.filter(school=school)
    if user.role == User.Role.TEACHER:
        teacher = get_object_or_404(Teacher, user=user, school=school); class_qs = class_qs.filter(teaching_assignments__teacher=teacher).distinct()
    school_class = get_object_or_404(class_qs, pk=selected) if selected else class_qs.first()
    if request.method == "POST" and school_class:
        students_qs = Student.objects.filter(enrollments__school_class=school_class, enrollments__is_active=True, is_active=True).distinct()
        with transaction.atomic():
            for student in students_qs:
                status = request.POST.get(f"status_{student.pk}", Attendance.Status.PRESENT)
                Attendance.objects.update_or_create(student=student, date=date, defaults={"school": school, "school_class": school_class, "status": status, "marked_by": user})
                if status == Attendance.Status.ABSENT and student.user:
                    Notification.objects.get_or_create(school=school, user=student.user, notification_type="ABSENCE", title="Attendance update", body=f"You were marked absent on {date}.", link=reverse("attendance"))
        audit(request, "Marked attendance", school_class, f"Attendance for {date}"); messages.success(request, f"Attendance for {school_class} saved.")
        return redirect(f"{reverse('attendance')}?class={school_class.pk}&date={date}")
    records = {r.student_id: r for r in Attendance.objects.filter(school=school, school_class=school_class, date=date)} if school_class else {}
    roster = Student.objects.filter(enrollments__school_class=school_class, enrollments__is_active=True, is_active=True).distinct() if school_class else []
    return render(request, "portal/attendance.html", {"classes": class_qs, "school_class": school_class, "date": date, "records": records, "roster": roster, "statuses": Attendance.Status.choices})


@roles_required(*ACADEMIC_STAFF_ROLES)
def assessments(request):
    school = school_for(request); qs = Assessment.objects.filter(school=school).select_related("school_class", "subject", "term", "teacher")
    if request.user.role == User.Role.TEACHER: qs = qs.filter(teacher__user=request.user)
    return render(request, "portal/assessments.html", {"assessments": paginate(request, qs), "can_create": request.user.role in ACADEMIC_STAFF_ROLES})


@roles_required(*ACADEMIC_STAFF_ROLES)
def assessment_create(request):
    school = school_for(request); teacher = Teacher.objects.filter(user=request.user, school=school).first(); form = AssessmentForm(request.POST or None, school=school, teacher=teacher if request.user.role == User.Role.TEACHER else None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school; obj.teacher = teacher or obj.teacher; obj.save(); audit(request, "Created assessment", obj); messages.success(request, "Assessment created. Enter marks when ready."); return redirect("mark_entry", pk=obj.pk)
    return render(request, "portal/form_page.html", {"form": form, "title": "Create assessment", "back_url": "assessments", "submit_label": "Create assessment"})


@roles_required(*ACADEMIC_STAFF_ROLES)
def mark_entry(request, pk):
    school = school_for(request); qs = Assessment.objects.filter(school=school)
    if request.user.role == User.Role.TEACHER: qs = qs.filter(teacher__user=request.user)
    assessment = get_object_or_404(qs.select_related("school_class", "subject", "term"), pk=pk)
    students_qs = Student.objects.filter(enrollments__school_class=assessment.school_class, enrollments__is_active=True).order_by("last_name", "first_name")
    existing = {m.student_id: m for m in Mark.objects.filter(assessment=assessment)}
    if request.method == "POST":
        with transaction.atomic():
            for student in students_qs:
                raw = request.POST.get(f"mark_{student.pk}", "").strip()
                comment = request.POST.get(f"comment_{student.pk}", "").strip()
                if not raw:
                    continue
                try: value = Decimal(raw)
                except Exception: messages.error(request, f"{student}: use a valid number."); return redirect("mark_entry", pk=pk)
                if value < 0 or value > assessment.maximum_mark: messages.error(request, f"{student}: mark must be between 0 and {assessment.maximum_mark}."); return redirect("mark_entry", pk=pk)
                Mark.objects.update_or_create(school=school, assessment=assessment, student=student, defaults={"obtained_mark": value, "teacher_comment": comment})
                if assessment.published and student.user:
                    Notification.objects.get_or_create(school=school, user=student.user, notification_type="RESULT", title="New result available", body=f"{assessment.subject.name}: {assessment.title}", link=reverse("my_results"))
        audit(request, "Entered assessment marks", assessment); messages.success(request, "Marks saved and grades calculated."); return redirect("mark_entry", pk=pk)
    return render(request, "portal/mark_entry.html", {"assessment": assessment, "students": students_qs, "existing": existing})


@roles_required(User.Role.STUDENT, User.Role.PARENT, *ADMIN_ROLES, User.Role.TEACHER)
def report_card(request, student_pk):
    school = school_for(request); student = get_object_or_404(Student, pk=student_pk, school=school)
    if request.user.role == User.Role.STUDENT and student.user_id != request.user.pk: return HttpResponseForbidden("You may view only your own report card.")
    if request.user.role == User.Role.PARENT and not student.parents.filter(user=request.user).exists(): return HttpResponseForbidden("You may view only report cards for your children.")
    term = Term.objects.filter(school=school, is_current=True).first() or Term.objects.filter(school=school).first()
    marks = Mark.objects.filter(student=student, assessment__published=True)
    if term: marks = marks.filter(assessment__term=term)
    marks = marks.select_related("assessment", "assessment__subject")
    total = marks.count(); average = sum((m.percentage for m in marks), 0) / total if total else 0
    attendance_qs = student.attendance_records
    at_total = attendance_qs.count(); at_good = attendance_qs.filter(status__in=["PRESENT", "LATE", "EXCUSED"]).count()
    return render(request, "portal/report_card.html", {"student": student, "marks": marks, "term": term, "average": round(average, 1), "attendance": round(at_good*100/at_total, 1) if at_total else 0})


def report_card_download(request, student_pk):
    school = school_for(request)
    student = get_object_or_404(Student, pk=student_pk, school=school)
    if request.user.role == User.Role.STUDENT and student.user_id != request.user.pk:
        return HttpResponseForbidden("You may download only your own report card.")
    if request.user.role == User.Role.PARENT and not student.parents.filter(user=request.user).exists():
        return HttpResponseForbidden("You may download only report cards for your children.")
    term = Term.objects.filter(school=school, is_current=True).first() or Term.objects.filter(school=school).first()
    marks = Mark.objects.filter(student=student, assessment__published=True)
    if term:
        marks = marks.filter(assessment__term=term)
    marks = marks.select_related("assessment", "assessment__subject")
    attendance_qs = student.attendance_records
    at_total = attendance_qs.count()
    at_good = attendance_qs.filter(status__in=["PRESENT", "LATE", "EXCUSED"]).count()
    attendance = round(at_good * 100 / at_total, 1) if at_total else 0

    buffer = BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("ReportHeading", parent=styles["Heading1"], alignment=TA_CENTER, textColor=colors.HexColor("#153b5b"))
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    story = [
        Paragraph(str(school.name), heading),
        Paragraph("STUDENT REPORT", ParagraphStyle("ReportTitle", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=12)),
        Spacer(1, 8),
        Table([
            ["Student name", f"{student.first_name} {student.last_name}", "Student number", student.student_number],
            ["Term", str(term) if term else "-", "Attendance", f"{attendance}%"],
        ], colWidths=[30 * mm, 65 * mm, 30 * mm, 55 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f6")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5dc")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
        ])),
        Spacer(1, 10),
    ]
    rows = [["Subject", "Assessment", "Mark", "%", "Grade", "Teacher comment"]]
    for mark in marks:
        rows.append([mark.assessment.subject.name, mark.assessment.title, f"{mark.obtained_mark} / {mark.assessment.maximum_mark}", str(mark.percentage), mark.grade, mark.teacher_comment or "-"])
    if len(rows) == 1:
        rows.append(["No published assessments for this report period.", "", "", "", "", ""])
    story.append(Table(rows, colWidths=[28 * mm, 37 * mm, 27 * mm, 15 * mm, 18 * mm, 55 * mm], repeatRows=1, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#153b5b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5dc")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])))
    document.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="report-card-{student.student_number}.pdf"'
    return response


@roles_required(User.Role.STUDENT)
def my_results(request):
    student = get_object_or_404(Student, user=request.user, school=school_for(request))
    marks = student.marks.filter(assessment__published=True).select_related("assessment", "assessment__subject")
    average = sum((mark.percentage for mark in marks), 0) / marks.count() if marks.exists() else 0
    return render(request, "portal/results.html", {"student": student, "marks": marks, "result_count": marks.count(), "average": round(average, 1)})


@roles_required(*ACADEMIC_STAFF_ROLES, User.Role.STUDENT, User.Role.PARENT)
def assignments(request):
    school = school_for(request); qs = Assignment.objects.filter(school=school).select_related("school_class", "subject", "teacher__user")
    if request.user.role == User.Role.TEACHER: qs = qs.filter(teacher__user=request.user)
    elif request.user.role == User.Role.STUDENT:
        student = get_object_or_404(Student, user=request.user, school=school); qs = qs.filter(school_class__enrollments__student=student, school_class__enrollments__is_active=True, published=True).distinct()
    elif request.user.role == User.Role.PARENT:
        parent = get_object_or_404(Parent, user=request.user, school=school); qs = qs.filter(school_class__enrollments__student__parents=parent, school_class__enrollments__is_active=True, published=True).distinct()
    page = paginate(request, qs)
    if request.user.role in ACADEMIC_STAFF_ROLES:
        for assignment in page:
            assignment.visible_submissions = assignment.submissions.filter(status__in=[AssignmentSubmission.Status.SUBMITTED, AssignmentSubmission.Status.LATE, AssignmentSubmission.Status.GRADED]).select_related("student")
    return render(request, "portal/assignments.html", {"assignments": page, "can_create": request.user.role in ACADEMIC_STAFF_ROLES})


@roles_required(*ACADEMIC_STAFF_ROLES, User.Role.STUDENT, User.Role.PARENT)
def assignment_attachment_download(request, pk):
    school = school_for(request)
    assignment = get_object_or_404(Assignment, pk=pk, school=school, published=True)
    if not assignment.attachment:
        raise Http404("This assignment has no attachment.")
    if request.user.role == User.Role.STUDENT:
        get_object_or_404(Student, user=request.user, school=school, enrollments__school_class=assignment.school_class, enrollments__is_active=True)
    elif request.user.role == User.Role.PARENT:
        get_object_or_404(Parent, user=request.user, school=school, children__enrollments__school_class=assignment.school_class, children__enrollments__is_active=True)
    elif request.user.role == User.Role.TEACHER and assignment.teacher and assignment.teacher.user_id != request.user.pk:
        return HttpResponseForbidden("You may download attachments only for your assignments.")
    return FileResponse(assignment.attachment.open("rb"), as_attachment=True, filename=os.path.basename(assignment.attachment.name))


@roles_required(*ACADEMIC_STAFF_ROLES)
def assignment_create(request):
    school = school_for(request); teacher = Teacher.objects.filter(user=request.user, school=school).first(); form = AssignmentForm(request.POST or None, request.FILES or None, school=school, teacher=teacher if request.user.role == User.Role.TEACHER else None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school; obj.teacher = teacher or obj.teacher; obj.save();
        for student in Student.objects.filter(enrollments__school_class=obj.school_class, enrollments__is_active=True, is_active=True):
            if student.user: Notification.objects.create(school=school, user=student.user, notification_type="ASSIGNMENT", title="New assignment", body=f"{obj.subject.name}: {obj.title}", link=reverse("assignments"))
        audit(request, "Created assignment", obj); messages.success(request, "Assignment published and students notified."); return redirect("assignments")
    return render(request, "portal/form_page.html", {"form": form, "title": "Create assignment", "back_url": "assignments", "submit_label": "Publish assignment"})


@roles_required(User.Role.STUDENT)
def assignment_submit(request, pk):
    school = school_for(request); student = get_object_or_404(Student, user=request.user, school=school); assignment = get_object_or_404(Assignment, pk=pk, school=school, school_class__enrollments__student=student, published=True)
    submission, _ = AssignmentSubmission.objects.get_or_create(school=school, assignment=assignment, student=student)
    form = SubmissionForm(request.POST or None, request.FILES or None, instance=submission)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.submitted_at = timezone.now(); obj.status = AssignmentSubmission.Status.LATE if timezone.now() > assignment.due_date else AssignmentSubmission.Status.SUBMITTED; obj.save(); audit(request, "Submitted assignment", obj); messages.success(request, "Your work has been submitted."); return redirect("assignments")
    return render(request, "portal/form_page.html", {"form": form, "title": f"Submit: {assignment.title}", "back_url": "assignments", "submit_label": "Submit work", "multipart": True})


@roles_required(*ACADEMIC_STAFF_ROLES, User.Role.STUDENT)
def submission_download(request, pk):
    school = school_for(request)
    submission = get_object_or_404(AssignmentSubmission.objects.select_related("assignment", "assignment__teacher", "student"), pk=pk, school=school)
    if not submission.attachment:
        raise Http404("This submission has no attachment.")
    if request.user.role == User.Role.STUDENT and submission.student.user_id != request.user.pk:
        return HttpResponseForbidden("You may download only your own submission.")
    if request.user.role == User.Role.TEACHER and (not submission.assignment.teacher or submission.assignment.teacher.user_id != request.user.pk):
        return HttpResponseForbidden("You may download submissions only for your assignments.")
    filename = f"{submission.student.student_number}-{os.path.basename(submission.attachment.name)}"
    return FileResponse(submission.attachment.open("rb"), as_attachment=True, filename=filename)


@roles_required(*ACADEMIC_STAFF_ROLES, User.Role.STUDENT, User.Role.PARENT)
def learning_materials(request):
    school = school_for(request); qs = LearningMaterial.objects.filter(school=school).select_related("subject", "form", "teacher__user").order_by("-uploaded_at")
    if request.user.role == User.Role.STUDENT:
        student = get_object_or_404(Student, user=request.user, school=school)
        forms = student.enrollments.filter(is_active=True).values_list("school_class__form", flat=True)
        qs = qs.filter(Q(form__isnull=True) | Q(form_id__in=forms))
    elif request.user.role == User.Role.PARENT:
        parent = get_object_or_404(Parent, user=request.user, school=school)
        forms = parent.children.filter(is_active=True).values_list("enrollments__school_class__form", flat=True)
        qs = qs.filter(Q(form__isnull=True) | Q(form_id__in=forms))
    return render(request, "portal/materials.html", {"materials": paginate(request, qs), "can_create": request.user.role in ACADEMIC_STAFF_ROLES})


@roles_required(*ACADEMIC_STAFF_ROLES)
def material_create(request):
    school = school_for(request); teacher = Teacher.objects.filter(user=request.user, school=school).first(); form = MaterialForm(request.POST or None, request.FILES or None, school=school)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school; obj.teacher = teacher; obj.save(); audit(request, "Uploaded learning material", obj); messages.success(request, "Learning material uploaded."); return redirect("learning_materials")
    return render(request, "portal/form_page.html", {"form": form, "title": "Upload learning material", "back_url": "learning_materials", "submit_label": "Upload", "multipart": True})


@roles_required(*FINANCE_ROLES)
def finance(request):
    school = school_for(request); query = request.GET.get("q", ""); qs = Invoice.objects.filter(school=school).select_related("student")
    if query: qs = qs.filter(Q(number__icontains=query) | Q(student__first_name__icontains=query) | Q(student__last_name__icontains=query))
    invoices_total = qs.exclude(status=Invoice.Status.VOID).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    collected = Payment.objects.filter(school=school).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return render(request, "portal/finance.html", {"invoices": paginate(request, qs), "q": query, "invoiced": invoices_total, "collected": collected, "outstanding": invoices_total-collected})


@roles_required(*FINANCE_ROLES)
def invoice_create(request):
    school = school_for(request); form = InvoiceForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school; obj.number = f"INV-{timezone.now():%Y%m%d}-{Invoice.objects.filter(school=school).count()+1:04d}"; obj.save(); audit(request, "Created invoice", obj); messages.success(request, "Invoice created."); return redirect("finance")
    return render(request, "portal/form_page.html", {"form": form, "title": "Create invoice", "back_url": "finance", "submit_label": "Create invoice"})


@roles_required(*FINANCE_ROLES)
def payment_create(request):
    school = school_for(request); form = PaymentForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school; obj.recorded_by = request.user; obj.receipt_number = f"RCT-{timezone.now():%Y%m%d}-{Payment.objects.filter(school=school).count()+1:04d}"; obj.save(); audit(request, "Recorded payment", obj); messages.success(request, f"Payment recorded. Receipt {obj.receipt_number} generated."); return redirect("receipt", pk=obj.pk)
    return render(request, "portal/form_page.html", {"form": form, "title": "Record payment", "back_url": "finance", "submit_label": "Record payment"})


@roles_required(*FINANCE_ROLES, User.Role.PARENT, User.Role.STUDENT)
def receipt(request, pk):
    school = school_for(request); payment = get_object_or_404(Payment.objects.select_related("invoice", "invoice__student", "recorded_by"), pk=pk, school=school)
    if request.user.role == User.Role.STUDENT and payment.invoice.student.user_id != request.user.pk: return HttpResponseForbidden("Not your receipt.")
    if request.user.role == User.Role.PARENT and not payment.invoice.student.parents.filter(user=request.user).exists(): return HttpResponseForbidden("Not your receipt.")
    return render(request, "portal/receipt.html", {"payment": payment})


@roles_required(*FINANCE_ROLES, User.Role.PARENT, User.Role.STUDENT)
def receipt_download(request, pk):
    school = school_for(request)
    payment = get_object_or_404(Payment.objects.select_related("invoice", "invoice__student", "recorded_by"), pk=pk, school=school)
    if request.user.role == User.Role.STUDENT and payment.invoice.student.user_id != request.user.pk:
        return HttpResponseForbidden("Not your receipt.")
    if request.user.role == User.Role.PARENT and not payment.invoice.student.parents.filter(user=request.user).exists():
        return HttpResponseForbidden("Not your receipt.")

    buffer = BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("ReceiptHeading", parent=styles["Heading1"], alignment=TA_CENTER, textColor=colors.HexColor("#153b5b"))
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=25 * mm, leftMargin=25 * mm, topMargin=25 * mm, bottomMargin=25 * mm)
    story = [
        Paragraph(str(school.name), heading),
        Paragraph("PAYMENT RECEIPT", ParagraphStyle("ReceiptTitle", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=13)),
        Spacer(1, 12),
    ]
    details = [
        ["Receipt number", payment.receipt_number],
        ["Received from", f"{payment.invoice.student.first_name} {payment.invoice.student.last_name}"],
        ["Amount paid", f"${payment.amount:,.2f}"],
        ["Invoice", payment.invoice.number],
        ["Payment date", payment.payment_date.strftime("%d %B %Y")],
        ["Payment method", payment.method],
        ["Reference", payment.reference or "-"],
        ["Remaining balance", f"${payment.invoice.balance:,.2f}"],
    ]
    story.append(Table(details, colWidths=[48 * mm, 92 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f6")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5dc")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ])))
    story.append(Spacer(1, 18))
    story.append(Paragraph(f"Recorded by {payment.recorded_by.display_name if payment.recorded_by else 'School accounts'}.", styles["BodyText"]))
    document.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt-{payment.receipt_number}.pdf"'
    return response


@roles_required(*FINANCE_ROLES, User.Role.PARENT, User.Role.STUDENT)
def my_fees(request, student_pk=None):
    school = school_for(request)
    if request.user.role == User.Role.STUDENT: student = get_object_or_404(Student, user=request.user, school=school)
    elif request.user.role == User.Role.PARENT:
        children = Student.objects.filter(school=school, parents__user=request.user, is_active=True).order_by("last_name", "first_name")
        student = get_object_or_404(children, pk=student_pk) if student_pk else children.first()
        if not student:
            return render(request, "portal/my_fees.html", {"student": None, "invoices": [], "balance": Decimal("0")})
    else: student = get_object_or_404(Student, pk=student_pk, school=school)
    invoices = student.invoices.prefetch_related("payments")
    total_fees = invoices.exclude(status=Invoice.Status.VOID).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    paid_fees = Payment.objects.filter(invoice__in=invoices).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return render(request, "portal/my_fees.html", {"student": student, "invoices": invoices, "balance": student_balance(student), "total_fees": total_fees, "paid_fees": paid_fees})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER, User.Role.BURSAR, User.Role.PARENT, User.Role.STUDENT)
def announcements(request):
    school = school_for(request); return render(request, "portal/announcements.html", {"announcements": visible_announcements(request.user), "can_create": request.user.role in (*ADMIN_ROLES, User.Role.TEACHER)})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def announcement_create(request):
    school = school_for(request); form = AnnouncementForm(request.POST or None, request.FILES or None, school=school)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school; obj.author = request.user; obj.save();
        recipients = User.objects.filter(school=school, is_active=True)
        if obj.audience == "TEACHERS": recipients = recipients.filter(role=User.Role.TEACHER)
        elif obj.audience == "STUDENTS": recipients = recipients.filter(role=User.Role.STUDENT)
        elif obj.audience == "PARENTS": recipients = recipients.filter(role=User.Role.PARENT)
        for user in recipients[:1000]: Notification.objects.create(school=school, user=user, notification_type="ANNOUNCEMENT", title="New announcement", body=obj.title, link=reverse("announcements"))
        audit(request, "Published announcement", obj); messages.success(request, "Announcement published."); return redirect("announcements")
    return render(request, "portal/form_page.html", {"form": form, "title": "Publish announcement", "back_url": "announcements", "submit_label": "Publish", "multipart": True})


@roles_required(User.Role.ADMIN, User.Role.PRINCIPAL, User.Role.TEACHER, User.Role.PARENT, User.Role.STUDENT, User.Role.BURSAR)
def messages_view(request):
    school = school_for(request); return render(request, "portal/messages.html", {"received": Message.objects.filter(school=school, recipient=request.user).select_related("sender"), "sent": Message.objects.filter(school=school, sender=request.user).select_related("recipient")})


@roles_required(User.Role.ADMIN, User.Role.PRINCIPAL, User.Role.TEACHER, User.Role.PARENT, User.Role.STUDENT, User.Role.BURSAR)
def message_create(request):
    school = school_for(request); form = MessageForm(request.POST or None, school=school, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.school = school; obj.sender = request.user; obj.save(); Notification.objects.create(school=school, user=obj.recipient, notification_type="MESSAGE", title="New message", body=obj.subject, link=reverse("messages")); audit(request, "Sent message", obj); messages.success(request, "Message sent."); return redirect("messages")
    return render(request, "portal/form_page.html", {"form": form, "title": "New message", "back_url": "messages", "submit_label": "Send message"})


@roles_required(User.Role.ADMIN, User.Role.PRINCIPAL, User.Role.TEACHER, User.Role.PARENT, User.Role.STUDENT, User.Role.BURSAR)
def notifications(request):
    school = school_for(request); notes = Notification.objects.filter(school=school, user=request.user)
    return render(request, "portal/notifications.html", {"notifications": notes})


@login_required
@require_POST
def notification_read(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user, school=school_for(request)); note.read_at = timezone.now(); note.save(update_fields=["read_at"]); return redirect(note.link or "notifications")


@roles_required(*ADMIN_ROLES, User.Role.TEACHER, User.Role.BURSAR)
def events(request):
    school = school_for(request); return render(request, "portal/events.html", {"events": Event.objects.filter(school=school), "can_create": request.user.role in (*ADMIN_ROLES, User.Role.TEACHER)})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def event_create(request):
    school = school_for(request); form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid(): obj = form.save(commit=False); obj.school=school; obj.created_by=request.user; obj.save(); audit(request, "Created event", obj); messages.success(request, "Event added to the calendar."); return redirect("events")
    return render(request, "portal/form_page.html", {"form": form, "title": "Create event", "back_url": "events", "submit_label": "Add event"})


@login_required
def timetable(request):
    school = school_for(request); user = request.user; chosen = request.GET.get("class")
    qs = TimetableSlot.objects.filter(school=school).select_related("subject", "teacher__user", "school_class")
    classes = SchoolClass.objects.filter(school=school)
    if user.role == User.Role.STUDENT:
        student = get_object_or_404(Student, user=user, school=school); school_class = student.enrollments.filter(is_active=True).values_list("school_class", flat=True).first(); qs = qs.filter(school_class_id=school_class); chosen = str(school_class or "")
    elif user.role == User.Role.TEACHER:
        qs = qs.filter(teacher__user=user)
    elif chosen: qs = qs.filter(school_class_id=chosen)
    slots = {(s.day, s.start_time.strftime("%H:%M")): s for s in qs}; times = sorted({s.start_time.strftime("%H:%M") for s in qs})
    return render(request, "portal/timetable.html", {"slots": slots, "times": times, "classes": classes, "chosen": chosen, "days": TimetableSlot.DAYS})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def timetable_slot_create(request):
    school = school_for(request)
    teacher = Teacher.objects.filter(user=request.user, school=school).first() if request.user.role == User.Role.TEACHER else None
    form = TimetableSlotForm(request.POST or None, school=school, teacher=teacher)
    if request.method == "POST" and form.is_valid():
        slot = form.save(commit=False)
        slot.school = school
        slot.save()
        audit(request, "Created timetable slot", slot)
        messages.success(request, "Timetable slot created.")
        return redirect("timetable")
    return render(request, "portal/form_page.html", {"form": form, "title": "Add timetable slot", "back_url": "timetable", "submit_label": "Create slot"})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
def timetable_slot_edit(request, pk):
    school = school_for(request)
    teacher = Teacher.objects.filter(user=request.user, school=school).first() if request.user.role == User.Role.TEACHER else None
    qs = TimetableSlot.objects.filter(school=school)
    if request.user.role == User.Role.TEACHER and teacher:
        qs = qs.filter(teacher=teacher)
    slot = get_object_or_404(qs, pk=pk)
    form = TimetableSlotForm(request.POST or None, instance=slot, school=school, teacher=teacher)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "Updated timetable slot", slot)
        messages.success(request, "Timetable slot updated.")
        return redirect("timetable")
    return render(request, "portal/form_page.html", {"form": form, "title": "Edit timetable slot", "back_url": "timetable", "submit_label": "Save changes"})


@roles_required(*ADMIN_ROLES, User.Role.TEACHER)
@require_POST
def timetable_slot_delete(request, pk):
    school = school_for(request)
    qs = TimetableSlot.objects.filter(school=school)
    if request.user.role == User.Role.TEACHER:
        qs = qs.filter(teacher__user=request.user)
    slot = get_object_or_404(qs, pk=pk)
    slot.delete()
    audit(request, "Deleted timetable slot", slot)
    messages.success(request, "Timetable slot removed.")
    return redirect("timetable")


@login_required
def profile(request):
    profile_user = request.user
    student_profile = Student.objects.filter(user=profile_user, school=profile_user.school).first() if profile_user.role == User.Role.STUDENT else None
    user_form = ProfileForm(request.POST or None, instance=profile_user)
    student_form = StudentProfileForm(request.POST or None, instance=student_profile) if student_profile else None
    if request.method == "POST" and user_form.is_valid() and (not student_form or student_form.is_valid()):
        user_form.save()
        if student_form:
            student_form.save()
        messages.success(request, "Your profile details have been updated.")
        return redirect("profile")
    return render(request, "portal/profile.html", {"profile_user": profile_user, "user_form": user_form, "student_form": student_form, "student_profile": student_profile})


@roles_required(User.Role.ADMIN, User.Role.PRINCIPAL, User.Role.TEACHER, User.Role.PARENT, User.Role.STUDENT, User.Role.BURSAR)
def global_search(request):
    school = school_for(request); q = request.GET.get("q", "").strip(); results = {}
    if q:
        if request.user.role in (User.Role.STUDENT, User.Role.PARENT):
            return render(request, "portal/search.html", {"q": q, "results": {}, "restricted_search": True})
        student_filter = Q(school=school)
        teacher_filter = Q(school=school)
        results = {
            "Students": Student.objects.filter(student_filter).filter(Q(first_name__icontains=q)|Q(last_name__icontains=q)|Q(student_number__icontains=q)).distinct()[:8],
            "Teachers": Teacher.objects.filter(teacher_filter).filter(Q(user__first_name__icontains=q)|Q(user__last_name__icontains=q)|Q(employee_number__icontains=q))[:8],
            "Subjects": Subject.objects.filter(school=school).filter(Q(name__icontains=q)|Q(code__icontains=q))[:8],
            "Invoices": Invoice.objects.filter(school=school).filter(Q(number__icontains=q)|Q(student__first_name__icontains=q)|Q(student__last_name__icontains=q))[:8],
        }
    return render(request, "portal/search.html", {"q": q, "results": results})
