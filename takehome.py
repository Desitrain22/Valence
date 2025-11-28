import jinja2

from django.db import models
from django.db.models import UniqueConstraint

from django.conf import settings

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='test-secret-key',
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
        ],
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        DEFAULT_AUTO_FIELD='django.db.models.AutoField',
    )
    
import django
django.setup()



def default_chat_stream():
    return {"messages": []}


class Prompt(models.Model):
    name = models.CharField(max_length=256)
    system_prompt = models.TextField()
    first_message = models.TextField()  # Always an assistant message.

    class Meta:
        app_label = 'test_app'
        constraints = [
            UniqueConstraint(fields=["name"], name="unique_prompt_name"),
        ]

    def materialize_chat(self, variables=None):
        if variables is None:
            variables = {}

        messages = [
            {"role": "system", "content": self._render(self.system_prompt, variables)},
            {
                "role": "assistant",
                "content": self._render(self.first_message, variables),
            },
        ]
        chat = Chat(messages=messages)
        chat.save()
        return chat

    def _render(self, message, variables):
        if variables is None:
            variables = {}

        # Gather all snippets
        snippets = dict([(s.name, s.content) for s in Snippet.objects.all()])

        # Recursively render all snippets
        rendered_snippets = {}
        visited = set()

        def render_snippet(name):
            if name in rendered_snippets:
                return rendered_snippets[name]
            if name in visited:
                raise ValueError(f"Circular dependency detected in snippet: {name}")

            visited.add(name)
            content = snippets.get(name, "")

            # Build context with variables and already-rendered snippets
            context = {**variables, **rendered_snippets}
            rendered = jinja2.Template(content).render(context)

            rendered_snippets[name] = rendered
            visited.remove(name)
            return rendered

        for name in snippets:
            render_snippet(name)
        context = rendered_snippets | variables
        return jinja2.Template(message).render(context)

    def __str__(self):
        return self.name


class Chat(models.Model):
    # We model chats as OpenAI does, like a list of messages:
    #
    # [
    #     {"role": "system", "content": "You are a helpful assistant."},
    #     {"role": "user", "content": "Knock knock."},
    #     {"role": "assistant", "content": "Who's there?"},
    #     {"role": "user", "content": "Orange."},
    # ]
    #
    # However, JSONField sometimes has issues with storing arrays outright, so
    # `stream` will always store an object with a single key: "messages", like so:
    #
    # {
    #    "messages": [
    #       {"role": "system", "content": "You are a helpful assistant."},
    #       {"role": "user", "content": "Knock knock."},
    #       {"role": "assistant", "content": "Who's there?"},
    #       {"role": "user", "content": "Orange."},
    #    ]
    # }
    stream = models.JSONField(default=default_chat_stream)

    class Meta:
        app_label = 'test_app'

    @property
    def messages(self):
        return self.stream["messages"]

    @messages.setter
    def messages(self, messages):
        self.stream["messages"] = messages


class Snippet(models.Model):
    name = models.CharField(max_length=256)
    content = models.TextField()

    class Meta:
        app_label = 'test_app'
        constraints = [
            UniqueConstraint(fields=["name"], name="unique_snippet_name"),
        ]

    def __str__(self):
        return self.name


if __name__ == "__main__":
    from django.core.management import call_command
    from django.db import connection
    
    # Create tables manually
    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(Snippet)
        schema_editor.create_model(Prompt)
        schema_editor.create_model(Chat)

    print("=" * 60)
    print("Test 1: Basic variable in snippet")
    print("=" * 60)
    
    Snippet.objects.create(name="greeting", content="Hello {{ name }}!")
    prompt = Prompt.objects.create(
        name="test1",
        system_prompt="{{ greeting }}",
        first_message="How can I help you?"
    )
    
    chat = prompt.materialize_chat({"name": "Alice"})
    print(f"System: {chat.messages[0]['content']}")
    print(f"Assistant: {chat.messages[1]['content']}")
    print()

    Snippet.objects.all().delete()
    Prompt.objects.all().delete()

    print("=" * 60)
    print("Test 2: Nested snippets")
    print("=" * 60)
    
    Snippet.objects.create(name="greeting", content="Hello {{ name }}!")
    Snippet.objects.create(name="welcome", content="{{ greeting }} Welcome to our service.")
    prompt = Prompt.objects.create(
        name="test2",
        system_prompt="{{ welcome }}",
        first_message="I'm here to assist you."
    )
    
    chat = prompt.materialize_chat({"name": "Bob"})
    print(f"System: {chat.messages[0]['content']}")
    print(f"Assistant: {chat.messages[1]['content']}")
    print()

    Snippet.objects.all().delete()
    Prompt.objects.all().delete()

    print("=" * 60)
    print("Test 3: Multiple variables")
    print("=" * 60)
    
    Snippet.objects.create(name="intro", content="Hi {{ name }}, you are a {{ role }}.")
    prompt = Prompt.objects.create(
        name="test3",
        system_prompt="{{ intro }} Be professional.",
        first_message="Ready to start!"
    )
    
    chat = prompt.materialize_chat({"name": "Charlie", "role": "developer"})
    print(f"System: {chat.messages[0]['content']}")
    print(f"Assistant: {chat.messages[1]['content']}")
    print()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)