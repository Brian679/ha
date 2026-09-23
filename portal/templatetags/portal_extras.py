from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Safe dictionary lookup for dynamic form rows."""
    try:
        return mapping.get(key)
    except (AttributeError, TypeError):
        return None


@register.simple_tag
def timetable_slot(slots, day, time):
    for slot in slots.values():
        if slot.day == day and slot.start_time.strftime("%H:%M") == time:
            return slot
    return None
