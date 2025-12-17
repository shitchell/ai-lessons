"""Command-line interface for ai-lessons."""

from __future__ import annotations

import click

from .admin import admin
from .contribute import contribute
from .recall import recall


@click.group()
@click.version_option()
def main():
    """AI Lessons - Knowledge management with semantic search.

    Commands are organized into three groups:

    \b
      admin       Database and system management
      contribute  Add and modify lessons, resources, and rules
      recall      Search and view lessons
    """
    pass


# Register command groups
main.add_command(admin)
main.add_command(contribute)
main.add_command(recall)


if __name__ == "__main__":
    main()
