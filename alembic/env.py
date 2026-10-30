"""从应用配置读取数据库，迁移与运行时始终使用同一连接设置。"""
from logging.config import fileConfig
from alembic import context
from app.database import Base, engine

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True, render_as_batch=connection.dialect.name == 'sqlite')
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=engine.url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get('connection') is not None:
    run(config.attributes['connection'])
else:
    with engine.connect() as connection:
        run(connection)
