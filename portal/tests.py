from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from .models import (
    AcademicYear, Assignment, AssignmentSubmission, Attendance, Form, Invoice,
    AdmissionApplication, Mark, Parent, Payment, School, SchoolClass, Student, StudentParent, Subject,
    Teacher, TeachingAssignment, Term, User,
)


class PortalWorkflowTests(TestCase):
    password = "TestPassword2026!"

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Test Horizon High", slug="test-horizon")
        cls.other_school = School.objects.create(name="Other High", slug="other-high")
        cls.year = AcademicYear.objects.create(school=cls.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), is_current=True)
        cls.term = Term.objects.create(school=cls.school, academic_year=cls.year, name="Term 1", number=1, start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), is_current=True)
        form = Form.objects.create(school=cls.school, name="Form 4", level=4)
        cls.school_class = SchoolClass.objects.create(school=cls.school, form=form, academic_year=cls.year, name="Form 4A")
        cls.subject = Subject.objects.create(school=cls.school, name="Mathematics", code="MATH", is_compulsory=True)
        cls.admin = cls.make_user("admin@test.edu", "Admin", "User", User.Role.ADMIN)
        teacher_user = cls.make_user("teacher@test.edu", "Sarah", "Teacher", User.Role.TEACHER)
        cls.teacher = Teacher.objects.create(school=cls.school, user=teacher_user, employee_number="T001")
        TeachingAssignment.objects.create(school=cls.school, teacher=cls.teacher, school_class=cls.school_class, subject=cls.subject)
        student_user = cls.make_user("student@test.edu", "Blessing", "Student", User.Role.STUDENT)
        cls.student = Student.objects.create(school=cls.school, user=student_user, student_number="S001", first_name="Blessing", last_name="Student", gender="FEMALE")
        cls.student.enrollments.create(school=cls.school, school_class=cls.school_class, academic_year=cls.year)
        parent_user = cls.make_user("parent@test.edu", "Tendai", "Parent", User.Role.PARENT)
        cls.parent = Parent.objects.create(school=cls.school, user=parent_user)
        StudentParent.objects.create(student=cls.student, parent=cls.parent, relationship="Parent", is_primary=True)
        cls.bursar = cls.make_user("bursar@test.edu", "Eunice", "Bursar", User.Role.BURSAR)
        cls.other_student = Student.objects.create(school=cls.other_school, student_number="O001", first_name="Other", last_name="Student", gender="MALE")

    @classmethod
    def make_user(cls, email, first, last, role):
        return User.objects.create_user(username=email, email=email, password=cls.password, first_name=first, last_name=last, school=cls.school, role=role)

    def login(self, email):
        self.assertTrue(self.client.login(email=email, password=self.password))

    def test_role_dashboards_are_available(self):
        for email in ["admin@test.edu", "teacher@test.edu", "student@test.edu", "parent@test.edu", "bursar@test.edu"]:
            self.login(email)
            self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
            self.client.logout()

    def test_student_can_download_own_report_card_pdf(self):
        self.login("student@test.edu")
        response = self.client.get(reverse("report_card_download", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment; filename=\"report-card-S001.pdf\"", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_student_can_download_authorized_receipt_pdf(self):
        invoice = Invoice.objects.create(school=self.school, number="INV-TEST-001", student=self.student, description="Term fees", due_date=date(2026, 3, 31), amount=Decimal("250.00"))
        payment = Payment.objects.create(school=self.school, receipt_number="RCT-TEST-001", invoice=invoice, amount=Decimal("100.00"), recorded_by=self.bursar)
        self.login("student@test.edu")
        response = self.client.get(reverse("receipt_download", args=[payment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment; filename=\"receipt-RCT-TEST-001.pdf\"", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

        other_user = self.make_user("other.receipt@test.edu", "Other", "Learner", User.Role.STUDENT)
        other_student = Student.objects.create(school=self.school, user=other_user, student_number="S003", first_name="Other", last_name="Learner", gender="MALE")
        self.client.logout()
        self.login(other_user.email)
        self.assertEqual(self.client.get(reverse("receipt_download", args=[payment.pk])).status_code, 403)

    def test_incomplete_student_account_gets_setup_page(self):
        user = self.make_user("incomplete.student@test.edu", "Incomplete", "Learner", User.Role.STUDENT)
        self.login(user.email)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Profile setup required", status_code=403)

    def test_school_boundary_hides_another_school_student(self):
        self.login("admin@test.edu")
        response = self.client.get(reverse("student_detail", args=[self.other_student.pk]))
        self.assertEqual(response.status_code, 404)

    def test_teacher_records_attendance(self):
        self.login("teacher@test.edu")
        response = self.client.post(reverse("attendance"), {"school_class": self.school_class.pk, "date": str(timezone.localdate()), f"status_{self.student.pk}": "LATE"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Attendance.objects.get(student=self.student, date=timezone.localdate()).status, "LATE")

    def test_marks_calculate_grade(self):
        from .models import Assessment
        assessment = Assessment.objects.create(school=self.school, title="Mathematics Test", assessment_type="TEST", school_class=self.school_class, subject=self.subject, term=self.term, teacher=self.teacher, maximum_mark=Decimal("100"), published=True)
        mark = Mark.objects.create(school=self.school, assessment=assessment, student=self.student, obtained_mark=Decimal("81"))
        self.assertEqual(mark.grade, "A")
        self.assertEqual(mark.percentage, 81.0)

    def test_teacher_marks_are_visible_to_student_after_publish(self):
        from .models import Assessment
        assessment = Assessment.objects.create(school=self.school, title="Term Mathematics Exam", assessment_type="ENDTERM", school_class=self.school_class, subject=self.subject, term=self.term, teacher=self.teacher, maximum_mark=Decimal("100"), published=True)
        self.login("teacher@test.edu")
        response = self.client.post(reverse("mark_entry", args=[assessment.pk]), {f"mark_{self.student.pk}": "86", f"comment_{self.student.pk}": "Excellent reasoning."})
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        self.login("student@test.edu")
        response = self.client.get(reverse("my_results"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Term Mathematics Exam")
        self.assertContains(response, "86")
        self.assertContains(response, "Excellent reasoning.")

    def test_student_submits_assignment(self):
        assignment = Assignment.objects.create(school=self.school, title="Algebra practice", description="Questions 1 to 10", school_class=self.school_class, subject=self.subject, teacher=self.teacher, due_date=timezone.now() + timedelta(days=1))
        self.login("student@test.edu")
        response = self.client.post(reverse("assignment_submit", args=[assignment.pk]), {"note": "My completed work."})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AssignmentSubmission.objects.get(assignment=assignment, student=self.student).status, "SUBMITTED")

    def test_student_and_teacher_can_download_assignment_files(self):
        assignment = Assignment.objects.create(
            school=self.school, title="Algebra practice", description="Questions 1 to 10",
            school_class=self.school_class, subject=self.subject, teacher=self.teacher,
            due_date=timezone.now() + timedelta(days=1),
            attachment=SimpleUploadedFile("questions.pdf", b"teacher questions"),
        )
        self.login("student@test.edu")
        response = self.client.get(reverse("assignment_attachment_download", args=[assignment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="questions.pdf"')
        self.assertEqual(response.content, b"teacher questions")

        submission = AssignmentSubmission.objects.create(
            school=self.school, assignment=assignment, student=self.student,
            submitted_at=timezone.now(), status=AssignmentSubmission.Status.SUBMITTED,
            attachment=SimpleUploadedFile("answers.docx", b"student answers"),
        )
        self.client.logout()
        self.login("teacher@test.edu")
        response = self.client.get(reverse("submission_download", args=[submission.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="S001-answers.docx"')
        self.assertEqual(response.content, b"student answers")

    def test_student_cannot_view_another_student_data(self):
        other_user = self.make_user("other.student@test.edu", "Other", "Learner", User.Role.STUDENT)
        other_student = Student.objects.create(school=self.school, user=other_user, student_number="S002", first_name="Other", last_name="Learner", gender="MALE")
        other_student.enrollments.create(school=self.school, school_class=self.school_class, academic_year=self.year)
        self.login("student@test.edu")
        self.assertEqual(self.client.get(reverse("report_card", args=[other_student.pk])).status_code, 403)
        search = self.client.get(reverse("search"), {"q": "Other"})
        self.assertEqual(search.status_code, 200)
        self.assertNotContains(search, "Other Learner")

    def test_student_can_manage_own_profile(self):
        self.login("student@test.edu")
        response = self.client.post(reverse("profile"), {"first_name": "Blessing", "last_name": "Student", "phone": "+263771112222", "address": "New address", "emergency_contact": "+263773334444"})
        self.assertRedirects(response, reverse("profile"))
        self.student.refresh_from_db()
        self.student.user.refresh_from_db()
        self.assertEqual(self.student.user.phone, "+263771112222")
        self.assertEqual(self.student.address, "New address")

    def test_teacher_can_create_student_account(self):
        self.login("teacher@test.edu")
        response = self.client.post(reverse("student_create"), {
            "student_number": "S999",
            "admission_number": "ADM-2026-999",
            "first_name": "New",
            "last_name": "Learner",
            "date_of_birth": "2013-05-18",
            "gender": "FEMALE",
            "nationality": "Zimbabwean",
            "address": "Bulawayo",
            "emergency_contact": "+263778888999",
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(school=self.school, student_number="S999", first_name="New").exists())

    def test_student_application_can_be_approved(self):
        response = self.client.post(reverse("admission_apply"), {
            "first_name": "Prospective",
            "last_name": "Student",
            "email": "prospective@example.com",
            "phone": "+263777000111",
            "date_of_birth": "2014-02-14",
            "gender": "MALE",
            "address": "Mutare",
            "additional_info": "Previous school: Sunshine Academy",
            "desired_class": self.school_class.pk,
            "password1": "SecurePass2026!",
            "password2": "SecurePass2026!",
        })
        self.assertEqual(response.status_code, 200)
        application = AdmissionApplication.objects.get(email="prospective@example.com")
        self.assertEqual(application.status, AdmissionApplication.Status.PENDING)
        self.assertRegex(application.application_number, r"^ADM-\d{4}-\d{4}$")
        self.assertEqual(application.desired_class, self.school_class)
        self.assertTrue(application.user)

        self.login("admin@test.edu")
        response = self.client.post(reverse("admission_approve", args=[application.pk]))
        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionApplication.Status.APPROVED)
        self.assertTrue(User.objects.filter(email="prospective@example.com", role=User.Role.STUDENT).exists())
        self.assertTrue(Student.objects.filter(school=self.school, user__email="prospective@example.com").exists())

    def test_application_tracking_returns_status(self):
        response = self.client.post(reverse("admission_apply"), {
            "first_name": "Trace",
            "last_name": "Applicant",
            "email": "trace@example.com",
            "phone": "+263777000222",
            "date_of_birth": "2014-03-10",
            "gender": "FEMALE",
            "address": "Harare",
        })
        self.assertEqual(response.status_code, 200)
        application = AdmissionApplication.objects.get(email="trace@example.com")
        application_number = application.application_number

        response = self.client.post(reverse("admission_track"), {
            "application_number": application_number,
            "email": "trace@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, application_number)
        self.assertContains(response, "Pending")

    def test_application_tracking_invalid_details_shows_error(self):
        response = self.client.post(reverse("admission_track"), {
            "application_number": "ADM-2026-0001",
            "email": "missing@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No application found with those details")

    def test_admin_can_view_application_detail(self):
        application = AdmissionApplication.objects.create(
            school=self.school, first_name="Detail", last_name="Applicant", email="detail@example.com",
            phone="+263777000333", gender="FEMALE", address="Harare", application_number="ADM-2026-0001",
            desired_class=self.school_class,
        )
        self.login("admin@test.edu")
        response = self.client.get(reverse("admission_detail", args=[application.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Applicant")
        self.assertContains(response, self.school_class.name)

    def test_applicant_can_view_own_status_after_login(self):
        application = AdmissionApplication.objects.create(
            school=self.school, first_name="Login", last_name="Applicant", email="login.applicant@example.com",
            phone="+263777000444", gender="MALE", address="Harare", application_number="ADM-2026-0002",
            desired_class=self.school_class,
            user=self.make_user("login.applicant@example.com", "Login", "Applicant", User.Role.STUDENT),
        )
        self.login("login.applicant@example.com")
        response = self.client.get(reverse("my_application_status"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ADM-2026-0002")
        self.assertContains(response, "Pending")

    def test_bursar_payment_updates_invoice_balance(self):
        invoice = Invoice.objects.create(school=self.school, number="INV-TEST-001", student=self.student, description="Term fees", due_date=date.today(), amount=Decimal("100"))
        self.login("bursar@test.edu")
        response = self.client.post(reverse("payment_create"), {"invoice": invoice.pk, "amount": "100.00", "payment_date": str(date.today()), "method": "Cash", "reference": "TEST", "notes": ""})
        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)
