"""Alembic environment configuration for AZUL.

This file configures the migration environment.
"""
from __future__ import with_statement
import os
import sys
from logging.config import dictConfig

from alembic import context

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in testruns:
config = context.config

# Interpret the config file for Python logging.
# This line sets up a basic logger for alembic.
if config.config_file_name is not None:
    dictConfig(
        {
            'version': 1,
            'formatters': {'default': {
                'format': '%(asctime)s %(levelname)-8s %(message)s',
            }},
            'handlers': {'console': {
                'class': 'logging.StreamHandler',
                'stream': sys.stdout,
                'formatter': 'default',
            }},
            'root': {'level': 'INFO', 'handlers': ['console']},
        }
    )

# add your model's MetaData object here
# for 'autogenerate' support
from client import db
target_metadata = db.metadata

# other values from the .ini file may be here:
# like sqlalchemy_url, etc.
def get_url():
    """Get database URL from environment.

    IMPORTANT: In production, DATABASE_URL must be set.
    Default fallback is for development only.
    """
    return os.environ.get(
        'DATABASE_URL',
        'sqlite:///instance/azul.db'
    )

def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    on this branch too.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = db.engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()