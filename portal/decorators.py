from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def roles_required(*roles):
    """Require an authenticated active account with one of the supplied roles."""
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_active or (user.school and not user.school.is_active):
                messages.error(request, "Your account or school is not active. Please contact support.")
                return redirect("login")
            if user.role not in roles:
                raise PermissionDenied("You do not have permission to access this page.")
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


STAFF_ROLES = ("ADMIN", "PRINCIPAL", "BURSAR")
ACADEMIC_STAFF_ROLES = ("ADMIN", "PRINCIPAL", "TEACHER")
