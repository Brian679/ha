from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.utils import timezone
from .models import (
    Announcement, Assignment, AssignmentSubmission, Attendance, Assessment, Event,
    AdmissionApplication, FeeStructure, Invoice, LearningMaterial, Mark, Message,
    Parent, Payment,
    School, SchoolClass, Student, Subject, Teacher, TeachingAssignment, TimetableSlot, User,
)


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"form-control {existing}".strip()
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "checkbox"


class PortalLoginForm(AuthenticationForm, StyledFormMixin):
    username = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@school.co.zw"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Your password"}))


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]


class StudentProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Student
        fields = ["address", "emergency_contact"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}


class StudentForm(StyledFormMixin, forms.ModelForm):
    email = forms.EmailField(required=False, help_text="Optional: this creates a student portal login.")
    password = forms.CharField(required=False, widget=forms.PasswordInput, help_text="Optional: set a temporary password for the student portal.")
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), required=False, label="Initial class")

    class Meta:
        model = Student
        fields = ["student_number", "admission_number", "first_name", "last_name", "date_of_birth", "gender", "nationality", "address", "photo", "emergency_contact", "is_active"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}), "address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, school=None, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            classes = SchoolClass.objects.filter(school=school)
            if teacher:
                classes = classes.filter(Q(teaching_assignments__teacher=teacher) | Q(class_teacher=teacher)).distinct()
            self.fields["school_class"].queryset = classes


class AdmissionApplicationForm(StyledFormMixin, forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Create a password", "autocomplete": "new-password"}), required=False, help_text="Optional: create a portal account to track this application.")
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm password", "autocomplete": "new-password"}), required=False)

    class Meta:
        model = AdmissionApplication
        fields = ["first_name", "last_name", "email", "phone", "date_of_birth", "gender", "address", "note", "additional_info", "desired_class", "supporting_document"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}), "address": forms.Textarea(attrs={"rows": 3}), "note": forms.Textarea(attrs={"rows": 3}), "additional_info": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields["desired_class"].queryset = SchoolClass.objects.filter(school=school).select_related("form", "academic_year")

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 or password2:
            if not password1:
                self.add_error("password1", "Please enter a password.")
            elif not password2:
                self.add_error("password2", "Please confirm your password.")
            elif password1 != password2:
                self.add_error("password2", "Passwords do not match.")
        return cleaned


class TeacherForm(StyledFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=40, required=False)
    employee_number = forms.CharField(max_length=30)
    qualification = forms.CharField(max_length=180, required=False)
    department = forms.CharField(max_length=80, required=False)
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, teacher=None, **kwargs):
        self.teacher = teacher
        initial = kwargs.setdefault("initial", {})
        if teacher:
            initial.update({"first_name": teacher.user.first_name, "last_name": teacher.user.last_name, "email": teacher.user.email, "phone": teacher.user.phone, "employee_number": teacher.employee_number, "qualification": teacher.qualification, "department": teacher.department, "is_active": teacher.is_active})
        super().__init__(*args, **kwargs)


class ClassForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ["form", "academic_year", "name", "stream", "class_teacher", "capacity"]

    def __init__(self, *args, school=None, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields["form"].queryset = self.fields["form"].queryset.filter(school=school)
            self.fields["academic_year"].queryset = self.fields["academic_year"].queryset.filter(school=school)
            self.fields["class_teacher"].queryset = self.fields["class_teacher"].queryset.filter(school=school)
        if teacher:
            self.fields["class_teacher"].queryset = self.fields["class_teacher"].queryset.filter(pk=teacher.pk)


class SubjectForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name", "code", "is_compulsory", "is_active"]


class AttendanceForm(StyledFormMixin, forms.Form):
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), label="Class")
    date = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school: self.fields["school_class"].queryset = SchoolClass.objects.filter(school=school)


class AssessmentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Assessment
        fields = ["title", "assessment_type", "school_class", "subject", "term", "date", "maximum_mark", "published"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, school=None, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields["school_class"].queryset = SchoolClass.objects.filter(school=school)
            self.fields["subject"].queryset = Subject.objects.filter(school=school)
            self.fields["term"].queryset = self.fields["term"].queryset.filter(school=school)
        if teacher:
            self.fields["school_class"].queryset = SchoolClass.objects.filter(teaching_assignments__teacher=teacher).distinct()
            self.fields["subject"].queryset = Subject.objects.filter(teaching_assignments__teacher=teacher).distinct()

    def clean(self):
        cleaned = super().clean()
        school_class, subject = cleaned.get("school_class"), cleaned.get("subject")
        if school_class and subject and not TeachingAssignment.objects.filter(school=school_class.school, school_class=school_class, subject=subject).exists():
            self.add_error("subject", "This subject is not assigned to the selected class.")
        return cleaned


class TimetableSlotForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TimetableSlot
        fields = ["school_class", "subject", "teacher", "day", "start_time", "end_time", "room"]
        widgets = {"start_time": forms.TimeInput(attrs={"type": "time"}), "end_time": forms.TimeInput(attrs={"type": "time"})}

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields["school_class"].queryset = SchoolClass.objects.filter(school=school)
            self.fields["subject"].queryset = Subject.objects.filter(school=school)
            self.fields["teacher"].queryset = Teacher.objects.filter(school=school)


class AssignmentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["title", "description", "school_class", "subject", "due_date", "attachment", "maximum_mark", "published"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4}), "due_date": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, school=None, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher:
            self.fields["school_class"].queryset = SchoolClass.objects.filter(teaching_assignments__teacher=teacher).distinct()
            self.fields["subject"].queryset = Subject.objects.filter(teaching_assignments__teacher=teacher).distinct()
        elif school:
            self.fields["school_class"].queryset = SchoolClass.objects.filter(school=school)
            self.fields["subject"].queryset = Subject.objects.filter(school=school)


class SubmissionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ["attachment", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 3, "placeholder": "Add a note for your teacher (optional)"})}


class PaymentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["invoice", "amount", "payment_date", "method", "reference", "notes"]
        widgets = {"payment_date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school: self.fields["invoice"].queryset = Invoice.objects.filter(school=school).exclude(status=Invoice.Status.VOID)

    def clean(self):
        cleaned = super().clean()
        invoice, amount = cleaned.get("invoice"), cleaned.get("amount")
        if invoice and amount and amount > invoice.balance:
            self.add_error("amount", f"Amount cannot exceed the outstanding balance of US${invoice.balance:,.2f}.")
        return cleaned


class InvoiceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["student", "description", "issue_date", "due_date", "amount"]
        widgets = {"issue_date": forms.DateInput(attrs={"type": "date"}), "due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school: self.fields["student"].queryset = Student.objects.filter(school=school, is_active=True)


class AnnouncementForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "message", "audience", "school_class", "form", "attachment", "expires_at"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5}), "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields["school_class"].queryset = SchoolClass.objects.filter(school=school)
            self.fields["form"].queryset = self.fields["form"].queryset.filter(school=school)


class MessageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Message
        fields = ["recipient", "subject", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, school=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields["recipient"].queryset = User.objects.filter(school=school, is_active=True).exclude(pk=getattr(user, "pk", None))


class EventForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "description", "starts_at", "ends_at", "audience"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}


class MaterialForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LearningMaterial
        fields = ["title", "description", "subject", "form", "topic", "file"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields["subject"].queryset = Subject.objects.filter(school=school)
            self.fields["form"].queryset = self.fields["form"].queryset.filter(school=school)
