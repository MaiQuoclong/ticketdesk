import factory
from django.core.files.base import ContentFile

from apps.accounts.models import User
from apps.tickets.models import Attachment, Category, Comment, Ticket


class UserFactory(factory.django.DjangoModelFactory[User]):
    class Meta:
        model = User
        django_get_or_create = ("username",)
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n:03d}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@ticketdesk.local")
    first_name = factory.Faker("first_name", locale="vi_VN")
    last_name = factory.Faker("last_name", locale="vi_VN")
    role = User.Role.CUSTOMER
    password = factory.PostGenerationMethodCall("set_password", "matkhau123")

    @factory.post_generation
    def save_password(obj, create, extracted, **kwargs):
        if create:
            obj.save()


class CustomerFactory(UserFactory):
    username = factory.Sequence(lambda n: f"khach{n:03d}")
    role = User.Role.CUSTOMER


class AgentFactory(UserFactory):
    username = factory.Sequence(lambda n: f"agent{n:03d}")
    role = User.Role.AGENT


class ManagerFactory(UserFactory):
    username = factory.Sequence(lambda n: f"quanly{n:03d}")
    role = User.Role.MANAGER
    is_staff = True


class CategoryFactory(factory.django.DjangoModelFactory[Category]):
    class Meta:
        model = Category
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Danh mục {n:03d}")
    description = factory.Faker("sentence", locale="vi_VN")


class TicketFactory(factory.django.DjangoModelFactory[Ticket]):
    class Meta:
        model = Ticket

    title = factory.Faker("sentence", nb_words=6, locale="vi_VN")
    description = factory.Faker("paragraph", locale="vi_VN")
    status = Ticket.Status.NEW
    priority = Ticket.Priority.MEDIUM
    category = factory.SubFactory(CategoryFactory)
    created_by = factory.SubFactory(CustomerFactory)
    assignee = None


class CommentFactory(factory.django.DjangoModelFactory[Comment]):
    class Meta:
        model = Comment

    ticket = factory.SubFactory(TicketFactory)
    author = factory.SelfAttribute("ticket.created_by")
    content = factory.Faker("paragraph", locale="vi_VN")
    is_internal = False


class AttachmentFactory(factory.django.DjangoModelFactory[Attachment]):
    class Meta:
        model = Attachment

    ticket = factory.SubFactory(TicketFactory)
    uploaded_by = factory.SelfAttribute("ticket.created_by")
    original_name = factory.Sequence(lambda n: f"anh_chup_{n:03d}.png")
    file = factory.LazyAttribute(lambda o: ContentFile(b"\x89PNG\r\n\x1a\n", name=o.original_name))
    size = 8
