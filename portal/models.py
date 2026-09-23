from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class School(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True)
    logo = models.ImageField(upload_to="school_logos/", blank=True, null=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    subscription_ends = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super administrator"
        ADMIN = "ADMIN", "School administrator"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"
        PARENT = "PARENT", "Parent / guardian"
        BURSAR = "BURSAR", "Bursar / accounts"
        PRINCIPAL = "PRINCIPAL", "Head / principal"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="users", blank=True, null=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STUDENT)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=40, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    email_verified = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        indexes = [models.Index(fields=["school", "role", "is_active"])]

    @property
    def display_name(self):
        return self.get_full_name().strip() or self.email


class TenantModel(models.Model):
    """Every school-owned record has this field to make tenant filtering explicit."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class AcademicYear(TenantModel):
    name = models.CharField(max_length=20)  # e.g. 2026
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="unique_school_academic_year")]
        ordering = ["-start_date"]

    def __str__(self): return self.name


class Term(TenantModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=40)
    number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(3)])
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["academic_year", "number"], name="unique_year_term_number")]
        ordering = ["academic_year", "number"]

    def __str__(self): return f"{self.academic_year} – Term {self.number}"


class Form(TenantModel):
    name = models.CharField(max_length=32)  # Form 1 ... Form 6
    level = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "level"], name="unique_school_form_level")]
        ordering = ["level"]

    def __str__(self): return self.name


class SchoolClass(TenantModel):
    form = models.ForeignKey(Form, on_delete=models.PROTECT, related_name="classes")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="classes")
    name = models.CharField(max_length=50)  # Form 4A
    stream = models.CharField(max_length=16, blank=True)
    class_teacher = models.ForeignKey("Teacher", on_delete=models.SET_NULL, blank=True, null=True, related_name="homeroom_classes")
    capacity = models.PositiveIntegerField(default=45)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "academic_year", "name"], name="unique_school_year_class")]
        ordering = ["form__level", "name"]

    def __str__(self): return self.name


class Parent(TenantModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_profile")
    relationship_default = models.CharField(max_length=30, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=100, blank=True)

    def __str__(self): return self.user.display_name


class Student(TenantModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile", blank=True, null=True)
    student_number = models.CharField(max_length=30)
    admission_number = models.CharField(max_length=30, blank=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=12, choices=[("MALE", "Male"), ("FEMALE", "Female"), ("OTHER", "Other")])
    nationality = models.CharField(max_length=60, default="Zimbabwean")
    address = models.TextField(blank=True)
    photo = models.ImageField(upload_to="students/", blank=True, null=True)
    emergency_contact = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    enrolled_at = models.DateField(default=timezone.localdate)
    parents = models.ManyToManyField(Parent, through="StudentParent", related_name="children")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "student_number"], name="unique_school_student_number")]
        indexes = [models.Index(fields=["school", "last_name", "first_name"]), models.Index(fields=["school", "is_active"])]
        ordering = ["last_name", "first_name"]

    def __str__(self): return f"{self.first_name} {self.last_name} ({self.student_number})"


class StudentParent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
    relationship = models.CharField(max_length=30, default="Guardian")
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "parent"], name="unique_student_parent")]


class AdmissionApplication(TenantModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=12, choices=[("MALE", "Male"), ("FEMALE", "Female"), ("OTHER", "Other")], blank=True)
    address = models.TextField(blank=True)
    note = models.TextField(blank=True)
    additional_info = models.TextField(blank=True)
    desired_class = models.ForeignKey("SchoolClass", on_delete=models.SET_NULL, blank=True, null=True, related_name="admission_applications")
    supporting_document = models.FileField(upload_to="admission_documents/", blank=True, null=True)
    application_number = models.CharField(max_length=32, unique=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="admission_applications")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, blank=True, null=True, related_name="admission_applications")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="approved_admissions")
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.status})"


class Teacher(TenantModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher_profile")
    employee_number = models.CharField(max_length=30)
    qualification = models.CharField(max_length=180, blank=True)
    hire_date = models.DateField(blank=True, null=True)
    department = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "employee_number"], name="unique_school_employee_number")]

    def __str__(self): return self.user.display_name


class Subject(TenantModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    is_compulsory = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "code"], name="unique_school_subject_code")]
        ordering = ["name"]

    def __str__(self): return f"{self.name} ({self.code})"


class TeachingAssignment(TenantModel):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="teaching_assignments")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="teaching_assignments")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="teaching_assignments")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["teacher", "school_class", "subject"], name="unique_teaching_assignment")]

    def __str__(self): return f"{self.teacher} — {self.school_class} {self.subject}"


class Enrollment(TenantModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="enrollments")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT)
    enrolled_on = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "school_class"], name="unique_student_class_enrollment")]
        indexes = [models.Index(fields=["school", "school_class", "is_active"])]


class Attendance(TenantModel):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        LATE = "LATE", "Late"
        EXCUSED = "EXCUSED", "Excused"
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "date"], name="unique_student_daily_attendance")]
        indexes = [models.Index(fields=["school", "date", "status"])]


class TimetableSlot(TenantModel):
    DAYS = [(1, "Monday"), (2, "Tuesday"), (3, "Wednesday"), (4, "Thursday"), (5, "Friday")]
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="timetable_slots")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, blank=True, null=True)
    day = models.PositiveSmallIntegerField(choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["day", "start_time"]


class Assessment(TenantModel):
    TYPES = [("TEST", "Test"), ("ASSIGNMENT", "Assignment"), ("PROJECT", "Project"), ("MIDTERM", "Mid-term examination"), ("ENDTERM", "End-of-term examination"), ("MOCK", "Mock examination")]
    title = models.CharField(max_length=160)
    assessment_type = models.CharField(max_length=16, choices=TYPES)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="assessments")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    term = models.ForeignKey(Term, on_delete=models.PROTECT)
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, related_name="assessments")
    date = models.DateField(default=timezone.localdate)
    maximum_mark = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    published = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date", "title"]


class Mark(TenantModel):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="marks")
    obtained_mark = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0)])
    grade = models.CharField(max_length=4, blank=True)
    teacher_comment = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assessment", "student"], name="unique_assessment_mark")]

    @property
    def percentage(self):
        return round((self.obtained_mark / self.assessment.maximum_mark) * 100, 1) if self.assessment.maximum_mark else 0

    def save(self, *args, **kwargs):
        percent = self.percentage
        self.grade = "A" if percent >= 75 else "B" if percent >= 65 else "C" if percent >= 50 else "D" if percent >= 40 else "E" if percent >= 30 else "U"
        super().save(*args, **kwargs)


class Assignment(TenantModel):
    title = models.CharField(max_length=160)
    description = models.TextField()
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="assignments")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, related_name="assignments")
    due_date = models.DateTimeField()
    attachment = models.FileField(upload_to="assignments/", blank=True, null=True)
    maximum_mark = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date"]


class AssignmentSubmission(TenantModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUBMITTED = "SUBMITTED", "Submitted"
        LATE = "LATE", "Late"
        GRADED = "GRADED", "Graded"
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="submissions")
    submitted_at = models.DateTimeField(blank=True, null=True)
    attachment = models.FileField(upload_to="submissions/", blank=True, null=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    mark = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    feedback = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assignment", "student"], name="unique_assignment_submission")]


class LearningMaterial(TenantModel):
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    form = models.ForeignKey(Form, on_delete=models.SET_NULL, blank=True, null=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, blank=True, null=True)
    topic = models.CharField(max_length=120, blank=True)
    file = models.FileField(upload_to="learning_materials/")
    uploaded_at = models.DateTimeField(auto_now_add=True)


class FeeStructure(TenantModel):
    name = models.CharField(max_length=120)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    form = models.ForeignKey(Form, on_delete=models.CASCADE, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    is_active = models.BooleanField(default=True)


class Invoice(TenantModel):
    class Status(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PARTIAL = "PARTIAL", "Partially paid"
        PAID = "PAID", "Paid"
        VOID = "VOID", "Void"
    number = models.CharField(max_length=32)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="invoices")
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.SET_NULL, blank=True, null=True)
    description = models.CharField(max_length=255)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "number"], name="unique_school_invoice_number")]
        ordering = ["-issue_date"]

    @property
    def amount_paid(self):
        return self.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    @property
    def balance(self): return self.amount - self.amount_paid

    def refresh_status(self):
        balance = self.balance
        self.status = self.Status.PAID if balance <= 0 else self.Status.PARTIAL if self.amount_paid else self.Status.UNPAID
        self.save(update_fields=["status"])


class Payment(TenantModel):
    receipt_number = models.CharField(max_length=32)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    payment_date = models.DateField(default=timezone.localdate)
    method = models.CharField(max_length=40, default="Cash")
    reference = models.CharField(max_length=80, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "receipt_number"], name="unique_school_receipt_number")]
        ordering = ["-payment_date"]


class Announcement(TenantModel):
    AUDIENCES = [("EVERYONE", "Everyone"), ("TEACHERS", "Teachers"), ("STUDENTS", "Students"), ("PARENTS", "Parents"), ("CLASS", "Specific class"), ("FORM", "Specific form")]
    title = models.CharField(max_length=180)
    message = models.TextField()
    audience = models.CharField(max_length=12, choices=AUDIENCES, default="EVERYONE")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.SET_NULL, blank=True, null=True)
    form = models.ForeignKey(Form, on_delete=models.SET_NULL, blank=True, null=True)
    attachment = models.FileField(upload_to="announcements/", blank=True, null=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    published_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-published_at"]


class Notification(TenantModel):
    TYPES = [("ASSIGNMENT", "Assignment"), ("RESULT", "New result"), ("ABSENCE", "Absence"), ("ANNOUNCEMENT", "Announcement"), ("FEES", "Fee reminder"), ("MESSAGE", "New message"), ("EXAM", "Examination reminder")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=255)
    notification_type = models.CharField(max_length=16, choices=TYPES)
    link = models.CharField(max_length=255, blank=True)
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Message(TenantModel):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_messages")
    subject = models.CharField(max_length=160)
    body = models.TextField()
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Event(TenantModel):
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(blank=True, null=True)
    audience = models.CharField(max_length=30, default="Everyone")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        ordering = ["starts_at"]


class DisciplineRecord(TenantModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        FOLLOW_UP = "FOLLOW_UP", "Follow-up"
        CLOSED = "CLOSED", "Closed"
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="discipline_records")
    incident_date = models.DateField()
    category = models.CharField(max_length=80)
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    follow_up = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    staff_member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)


class Document(TenantModel):
    title = models.CharField(max_length=150)
    category = models.CharField(max_length=80)
    file = models.FileField(upload_to="documents/")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, blank=True, null=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, blank=True, null=True)
    visibility = models.CharField(max_length=30, default="Staff")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class AuditLog(TenantModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    action = models.CharField(max_length=120)
    record_type = models.CharField(max_length=80)
    record_id = models.CharField(max_length=64, blank=True)
    detail = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "created_at"])]
