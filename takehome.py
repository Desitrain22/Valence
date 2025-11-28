import jinja2

from django.db import models
from django.db.models import UniqueConstraint


def default_chat_stream():
    return {"messages": []}


class Prompt(models.Model):
    name = models.CharField(max_length=256)
    system_prompt = models.TextField()
    first_message = models.TextField()  # Always an assistant message.

    class Meta:
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

        # Render all snippets
        for name in snippets:
            render_snippet(name)

        # Merge rendered snippets and variables for final context
        context = rendered_snippets | variables

        # Render the message with the full context
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
        constraints = [
            UniqueConstraint(fields=["name"], name="unique_snippet_name"),
        ]

    def __str__(self):
        return self.name
