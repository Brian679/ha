from datetime import date, datetime, time, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from portal.models import (
    AcademicYear, Announcement, Assignment, AssignmentSubmission, Attendance,
    Assessment, Event, FeeStructure, Form, Invoice, Mark, Parent, Payment,
    School, SchoolClass, Student, StudentParent, Subject, Teacher,
    TeachingAssignment, Term, TimetableSlot, User,
)


PASSWORD = "Demo@2026!"


class Command(BaseCommand):
    help = "Create a complete, safe-to-reset Higher Achievers demonstration school."

    def user(self, school, email, first, last, role, username=None):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": username or email.split("@")[0], "first_name": first, "last_name": last, "school": school, "role": role, "email_verified": True},
        )
        if created:
            user.set_password(PASSWORD)
            user.save()
        return user

    @transaction.atomic
    def handle(self, *args, **options):
        school, created = School.objects.get_or_create(
            slug="higher-achievers",
            defaults={"name": "Higher Achievers", "address": "18 Samora Machel Avenue, Harare", "phone": "+263 24 200 0145", "email": "info@higherachievers.co.zw", "website": "https://higherachievers.co.zw"},
        )
        if not created:
            self.stdout.write(self.style.WARNING("Demo school already exists; preserving the existing records."))
            return

        current_year = AcademicYear.objects.create(school=school, name="2026", start_date=date(2026, 1, 13), end_date=date(2026, 12, 4), is_current=True)
        terms = [Term.objects.create(school=school, academic_year=current_year, name=f"Term {number}", number=number, start_date=start, end_date=end, is_current=number == 2) for number, start, end in [
            (1, date(2026, 1, 13), date(2026, 4, 3)), (2, date(2026, 5, 5), date(2026, 8, 7)), (3, date(2026, 9, 8), date(2026, 12, 4)),
        ]]
        forms = {level: Form.objects.create(school=school, name=f"Form {level}", level=level) for level in range(1, 5)}

        principal = self.user(school, "principal@demo-school.com", "Miriam", "Chikore", User.Role.PRINCIPAL)
        admin = self.user(school, "admin@demo-school.com", "Tariro", "Moyo", User.Role.ADMIN)
        bursar = self.user(school, "bursar@demo-school.com", "Eunice", "Sibanda", User.Role.BURSAR)

        teacher_names = [("Sarah", "Ndlovu"), ("Farai", "Dube"), ("Rudo", "Mare"), ("Kudzanai", "Mutsvairo"), ("Tendai", "Mlambo"), ("Lillian", "Moyo"), ("Brian", "Mukwashi"), ("Faith", "Chirima"), ("Collins", "Ncube"), ("Patience", "Mupfumi")]
        teachers = []
        for index, (first, last) in enumerate(teacher_names, 1):
            email = "teacher@demo-school.com" if index == 1 else f"{first.lower()}.{last.lower()}@demo-school.com"
            user = self.user(school, email, first, last, User.Role.TEACHER, f"teacher-{index}")
            teacher = Teacher.objects.create(school=school, user=user, employee_number=f"TCH-{index:03d}", qualification="Bachelor of Education", department=["Sciences", "Languages", "Commercials", "Humanities"][index % 4], hire_date=date(2022, 1, min(index, 28)))
            teachers.append(teacher)

        classes = {}
        index = 0
        for level in range(1, 5):
            for stream in ("A", "B"):
                name = f"Form {level}{stream}"
                classes[name] = SchoolClass.objects.create(school=school, form=forms[level], academic_year=current_year, name=name, stream=stream, class_teacher=teachers[index % len(teachers)], capacity=45)
                index += 1
        demo_class = classes["Form 4A"]

        subject_data = [
            ("Mathematics", "MATH", True), ("English Language", "ENGL", True), ("Shona", "SHON", True), ("Combined Science", "SCI", True),
            ("Geography", "GEOG", False), ("History", "HIST", False), ("Business Studies", "BUS", False), ("Accounting", "ACCT", False),
            ("Computer Science", "COMP", False), ("ICT", "ICT", False), ("Agriculture", "AGRI", False), ("Physics", "PHYS", False),
        ]
        subjects = {code: Subject.objects.create(school=school, name=name, code=code, is_compulsory=compulsory) for name, code, compulsory in subject_data}
        for c_index, school_class in enumerate(classes.values()):
            for s_index, subject in enumerate(subjects.values()):
                if s_index < 5 or (school_class.form.level >= 3 and s_index < 9):
                    TeachingAssignment.objects.create(school=school, teacher=teachers[(s_index + c_index) % len(teachers)], school_class=school_class, subject=subject)
        # The documented demo teacher owns Mathematics in Form 4A.
        TeachingAssignment.objects.filter(school=school, school_class=demo_class, subject=subjects["MATH"]).update(teacher=teachers[0])

        first_names = ["Blessing", "Tanaka", "Tafadzwa", "Nyasha", "Rutendo", "Kudzai", "Tapiwa", "Anesu", "Munyaradzi", "Rumbidzai", "Tinashe", "Chiedza", "Kudakwashe", "Tariro", "Simba", "Fadzai", "Tatenda", "Ropafadzo", "Vimbai", "Munashe"]
        last_names = ["Moyo", "Ncube", "Dube", "Sibanda", "Mare", "Ndlovu", "Chikore", "Mlambo", "Mupfumi", "Chirima"]
        students = []
        class_values = list(classes.values())
        for index in range(100):
            first, last = first_names[index % len(first_names)], last_names[(index * 3) % len(last_names)]
            number = f"HHS-2026-{index + 1:03d}"
            email = "student@demo-school.com" if index == 0 else f"student{index + 1}@demo-school.com"
            user = self.user(school, email, first, last, User.Role.STUDENT, f"student-{index+1}")
            student = Student.objects.create(school=school, user=user, student_number=number, admission_number=f"ADM-{2020 + (index % 4)}-{index + 1:03d}", first_name=first, last_name=last, date_of_birth=date(2010 - (index % 3), (index % 12) + 1, (index % 27) + 1), gender="FEMALE" if index % 2 else "MALE", address="Harare, Zimbabwe", emergency_contact="+263 77 000 0000")
            school_class = demo_class if index == 0 else class_values[index % len(class_values)]
            student.enrollments.create(school=school, school_class=school_class, academic_year=current_year)
            students.append(student)

        # Fifty guardians, usually shared by two learners, with the first account retained as the documented demo login.
        for index in range(50):
            first = ["Tendai", "Ruth", "Sipiwe", "James", "Chipo"][index % 5]
            last = last_names[index % len(last_names)]
            email = "parent@demo-school.com" if index == 0 else f"parent{index + 1}@demo-school.com"
            user = self.user(school, email, first, last, User.Role.PARENT, f"parent-{index+1}")
            parent = Parent.objects.create(school=school, user=user, relationship_default="Parent", occupation="Professional", address="Harare, Zimbabwe")
            for student in students[index * 2:index * 2 + 2]:
                StudentParent.objects.create(student=student, parent=parent, relationship="Parent", is_primary=True)

        # A Form 4A timetable and complete academic flow for the documented teacher and learner.
        form_4a = classes["Form 4A"]
        math_teacher = teachers[0]
        math = subjects["MATH"]
        slots = [(1, time(7, 30), time(8, 35), math, math_teacher, "B12"), (2, time(8, 40), time(9, 45), subjects["ENGL"], teachers[1], "B12"), (3, time(7, 30), time(8, 35), subjects["SCI"], teachers[3], "Lab 2"), (4, time(9, 50), time(10, 55), subjects["GEOG"], teachers[4], "C04"), (5, time(10, 55), time(12, 0), math, math_teacher, "B12")]
        for day, start, end, subject, teacher, room in slots:
            TimetableSlot.objects.create(school=school, school_class=form_4a, subject=subject, teacher=teacher, day=day, start_time=start, end_time=end, room=room)

        today = timezone.localdate()
        previous_days = [today - timedelta(days=offset) for offset in range(0, 7) if (today - timedelta(days=offset)).weekday() < 5]
        for day in previous_days:
            for student in students:
                status = "ABSENT" if (student.pk + day.day) % 19 == 0 else "LATE" if (student.pk + day.day) % 13 == 0 else "PRESENT"
                school_class = student.enrollments.first().school_class
                Attendance.objects.create(school=school, student=student, school_class=school_class, date=day, status=status, marked_by=teachers[(student.pk or 1) % len(teachers)].user)

        assessment = Assessment.objects.create(school=school, title="Mathematics Mid-term Test", assessment_type="MIDTERM", school_class=form_4a, subject=math, term=terms[1], teacher=math_teacher, date=today - timedelta(days=6), maximum_mark=Decimal("100"), published=True)
        form_4a_students = list(Student.objects.filter(enrollments__school_class=form_4a, enrollments__is_active=True))
        for index, student in enumerate(form_4a_students):
            Mark.objects.create(school=school, assessment=assessment, student=student, obtained_mark=Decimal(str(55 + (index * 7) % 39)), teacher_comment="Good progress." if index % 3 else "Keep practising algebra.")
        assignment = Assignment.objects.create(school=school, title="Quadratic equations practice", description="Complete questions 1–20, showing all working clearly.", school_class=form_4a, subject=math, teacher=math_teacher, due_date=timezone.now() + timedelta(days=5), maximum_mark=Decimal("30"))
        for index, student in enumerate(form_4a_students[:9]):
            if index < 5:
                AssignmentSubmission.objects.create(school=school, assignment=assignment, student=student, submitted_at=timezone.now() - timedelta(hours=index), note="Submitted through the learner portal.", status="SUBMITTED")

        fee_structure = FeeStructure.objects.create(school=school, name="Term 2 tuition and levy", term=terms[1], amount=Decimal("680.00"), due_date=date(2026, 6, 6))
        for index, student in enumerate(students):
            invoice = Invoice.objects.create(school=school, number=f"INV-2026-{index+1:04d}", student=student, fee_structure=fee_structure, description="Term 2 tuition and levy", issue_date=date(2026, 5, 5), due_date=date(2026, 6, 6), amount=Decimal("680.00"))
            if index < 72:
                amount = Decimal("680.00") if index % 3 else Decimal("350.00")
                Payment.objects.create(school=school, receipt_number=f"RCT-2026-{index+1:04d}", invoice=invoice, amount=amount, payment_date=date(2026, 5, min(5 + index % 20, 28)), method="EcoCash" if index % 2 else "Bank transfer", reference=f"DEMO-{index+1:04d}", recorded_by=bursar)

        Announcement.objects.create(school=school, title="Term 2 assessment schedule", message="Mid-term assessment preparation begins next week. Learners should check their subject timetables and teachers’ guidance.", audience="EVERYONE", author=admin)
        Announcement.objects.create(school=school, title="Form 4 revision session", message="Mathematics revision is scheduled for Thursday at 15:30 in B12.", audience="CLASS", school_class=form_4a, author=math_teacher.user)
        Event.objects.create(school=school, title="Term 2 Mid-term examinations", description="Assessment week for all forms.", starts_at=timezone.make_aware(datetime.combine(today + timedelta(days=14), time(8, 0))), ends_at=timezone.make_aware(datetime.combine(today + timedelta(days=18), time(15, 0))), audience="Students and teachers", created_by=admin)

        self.stdout.write(self.style.SUCCESS("Demo school created."))
        self.stdout.write("Demo credentials (all use Demo@2026!):")
        for email in ["admin@demo-school.com", "teacher@demo-school.com", "student@demo-school.com", "parent@demo-school.com", "bursar@demo-school.com", "principal@demo-school.com"]:
            self.stdout.write(f"  {email}")
