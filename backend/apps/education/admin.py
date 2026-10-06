from django.contrib import admin
from .models import (
    Family,
    Student,
    GuardianLink,
    Tutor,
    Subject,
    Resource,
    TeachingRequest,
)

for model in (Family, Student, GuardianLink, Tutor, Subject, Resource):
    admin.site.register(model)

from .models import (
    LearningPath,
    PathEnrollment,
    TeachingGroup,
    GroupMembership,
    CurriculumBlock,
    RequestParticipant,
)


class PathReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (
    LearningPath,
    PathEnrollment,
    TeachingGroup,
    GroupMembership,
    CurriculumBlock,
    RequestParticipant,
):
    admin.site.register(model, PathReadOnlyAdmin)


@admin.register(TeachingRequest)
class TeachingRequestAdmin(admin.ModelAdmin):
    exclude = ("curriculum_block", "source_fingerprint")

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (
            obj is None or obj.curriculum_block_id is None
        )

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (
            obj is None or obj.curriculum_block_id is None
        )
