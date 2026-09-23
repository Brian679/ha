from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *


@admin.register(User)
class PortalUserAdmin(UserAdmin):
    list_display = ("email", "first_name", "last_name", "school", "role", "is_active")
    list_filter = ("school", "role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Portal access", {"fields": ("school", "role", "phone", "avatar", "email_verified", "must_change_password")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Portal access", {"fields": ("email", "school", "role")}),)
    ordering = ("email",)


for model in [School, AcademicYear, Term, Form, SchoolClass, Student, Parent, Teacher, Subject, TeachingAssignment, Enrollment, Attendance, TimetableSlot, Assessment, Mark, Assignment, AssignmentSubmission, LearningMaterial, FeeStructure, Invoice, Payment, Announcement, Notification, Message, Event, DisciplineRecord, Document, AuditLog]:
    admin.site.register(model)
