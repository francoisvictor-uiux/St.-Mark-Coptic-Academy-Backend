"""Seed the RBAC catalog (spec Part 0 §2.2) and starter roles (§2.3). Idempotent."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.rbac.models import Module, ModuleGroup, Permission, Role, RolePermission

# (key, name_ar, name_en, group, [actions])
MODULES = [
    ("articles", "المقالات", "Articles", ModuleGroup.CONTENT,
     ["view", "create", "edit", "delete", "publish", "approve", "export", "archive", "restore"]),
    ("research", "الأبحاث", "Research Papers", ModuleGroup.ACADEMIC,
     ["view", "create", "edit", "delete", "publish", "approve", "export", "archive", "restore"]),
    ("theses", "رسائل الماجستير", "Master's Theses", ModuleGroup.ACADEMIC,
     ["view", "create", "edit", "delete", "publish", "approve", "export", "archive", "restore"]),
    ("dissertations", "أطروحات الدكتوراه", "PhD Dissertations", ModuleGroup.ACADEMIC,
     ["view", "create", "edit", "delete", "publish", "approve", "export", "archive", "restore"]),
    ("books", "الكتب", "Books", ModuleGroup.ACADEMIC,
     ["view", "create", "edit", "delete", "publish", "export", "import", "archive", "restore"]),
    ("events", "الفعاليات", "Events", ModuleGroup.EVENTS,
     ["view", "create", "edit", "delete", "publish", "approve", "export", "archive", "restore"]),
    ("news", "الأخبار", "News", ModuleGroup.CONTENT,
     ["view", "create", "edit", "delete", "publish", "archive", "restore"]),
    ("pages", "صفحات الموقع", "Website Pages", ModuleGroup.CONTENT,
     ["view", "create", "edit", "delete", "publish"]),
    ("homepage", "الصفحة الرئيسية", "Homepage", ModuleGroup.CONTENT,
     ["view", "edit", "publish"]),
    ("media", "الوسائط", "Media Library", ModuleGroup.CONTENT,
     ["view", "create", "edit", "delete", "import"]),
    ("categories", "التصنيفات", "Categories", ModuleGroup.CONTENT,
     ["view", "create", "edit", "delete"]),
    ("programs", "البرامج الدراسية", "Programs", ModuleGroup.ACADEMIC,
     ["view", "create", "edit", "delete", "publish", "archive", "restore"]),
    ("admissions", "القبول", "Admissions", ModuleGroup.ACADEMIC,
     ["view", "edit", "approve", "export", "assign"]),
    ("faqs", "الأسئلة الشائعة", "FAQs", ModuleGroup.CONTENT,
     ["view", "create", "edit", "delete", "publish"]),
    ("contact", "رسائل التواصل", "Contact Messages", ModuleGroup.CONTENT,
     ["view", "edit", "export"]),
    ("menus", "القوائم", "Menus", ModuleGroup.CONTENT,
     ["view", "create", "edit", "delete"]),
    ("users", "المستخدمون", "Users", ModuleGroup.SYSTEM,
     ["view", "create", "edit", "delete", "approve", "export", "assign"]),
    ("roles", "الأدوار والصلاحيات", "Roles", ModuleGroup.SYSTEM,
     ["view", "create", "edit", "delete", "assign"]),
    ("settings", "الإعدادات", "Settings", ModuleGroup.SYSTEM,
     ["view", "edit"]),
    ("analytics", "الإحصائيات", "Analytics", ModuleGroup.SYSTEM,
     ["view", "export"]),
    ("audit", "سجل النشاط", "Audit Log", ModuleGroup.SYSTEM,
     ["view", "export"]),
]

# Guarded: only Super Admin can grant (spec §2.2 rules)
GUARDED = {"users.*", "roles.*", "settings.edit", "audit.view"}

# Soft dependencies within a module (spec §2.2): action -> required actions
DEPENDENCIES = {
    "edit": ["view"],
    "publish": ["edit"],
    "restore": ["archive"],
}

# slug, name_ar, name_en, description, bundle {module: [actions] or "*"}
SEED_ROLES = [
    ("content-editor", "محرر المحتوى", "Content Editor",
     "إنشاء وتحرير المقالات والأخبار وصفحات الموقع",
     {"articles": ["view", "create", "edit"], "news": ["view", "create", "edit"],
      "pages": ["view", "create", "edit"], "faqs": ["view", "create", "edit"],
      "media": ["view", "create"]}),
    ("research-manager", "مدير الأبحاث", "Research Manager",
     "إدارة كاملة للأبحاث ورسائل الماجستير وأطروحات الدكتوراه",
     {"research": "*", "theses": "*", "dissertations": "*"}),
    ("library-manager", "مدير المكتبة", "Library Manager",
     "إدارة الكتب والتصنيفات بما يشمل الاستيراد",
     {"books": "*", "categories": ["view", "create", "edit"]}),
    ("events-manager", "مدير الفعاليات", "Events Manager",
     "إدارة كاملة للفعاليات",
     {"events": "*", "media": ["view", "create"]}),
    ("admission-officer", "مسؤول القبول", "Admission Officer",
     "مراجعة طلبات الالتحاق والموافقة عليها",
     {"admissions": ["view", "edit", "approve", "export", "assign"], "programs": ["view"]}),
    ("moderator", "مراقب المحتوى", "Moderator",
     "مراجعة واعتماد المحتوى دون إنشاء أو حذف",
     {"articles": ["view", "approve"], "research": ["view", "approve"],
      "theses": ["view", "approve"], "dissertations": ["view", "approve"],
      "events": ["view", "approve"], "news": ["view"], "books": ["view"],
      "pages": ["view"], "homepage": ["view"]}),
]


def is_guarded(module_key: str, action: str) -> bool:
    return f"{module_key}.{action}" in GUARDED or f"{module_key}.*" in GUARDED


class Command(BaseCommand):
    help = "Seed RBAC modules, permissions catalog, and starter roles (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        created = {"modules": 0, "permissions": 0, "roles": 0, "grants": 0}

        perm_by_code = {}
        for sort, (key, name_ar, name_en, group, actions) in enumerate(MODULES):
            module, was_new = Module.objects.update_or_create(
                key=key,
                defaults={"name_ar": name_ar, "name_en": name_en, "group": group,
                          "sort_order": sort, "is_active": True},
            )
            created["modules"] += was_new
            for action in actions:
                deps = [f"{key}.{dep}" for dep in DEPENDENCIES.get(action, []) if dep in actions]
                perm, was_new = Permission.objects.update_or_create(
                    module=module, action=action,
                    defaults={"is_guarded": is_guarded(key, action), "depends_on": deps},
                )
                created["permissions"] += was_new
                perm_by_code[f"{key}.{action}"] = perm

        module_actions = {key: actions for key, _, _, _, actions in MODULES}
        for slug, name_ar, name_en, description, bundle in SEED_ROLES:
            role, was_new = Role.objects.update_or_create(
                slug=slug,
                defaults={"name_ar": name_ar, "name_en": name_en,
                          "description": description, "is_system": False},
            )
            created["roles"] += was_new
            for module_key, actions in bundle.items():
                if actions == "*":
                    actions = module_actions[module_key]
                for action in actions:
                    _, was_new = RolePermission.objects.get_or_create(
                        role=role, permission=perm_by_code[f"{module_key}.{action}"]
                    )
                    created["grants"] += was_new

        self.stdout.write(self.style.SUCCESS(
            "RBAC seeded — new: {modules} modules, {permissions} permissions, "
            "{roles} roles, {grants} grants".format(**created)
        ))
