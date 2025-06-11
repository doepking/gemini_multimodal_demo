import os
import logging
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from google.cloud.sql.connector import Connector, IPTypes
import pg8000

# Import Base from models.py, it's needed for init_db
from models import Base

# Configure logging - using the "app" logger for consistency,
# or you could define a new one like logging.getLogger("database")
logger = logging.getLogger("app")

# --- Database Configuration and Setup ---
INSTANCE_CONNECTION_NAME = os.environ.get("CLOUD_SQL_CONNECTION_NAME")
DB_USER = os.environ.get("CLOUD_SQL_USER")
DB_PASS = os.environ.get("CLOUD_SQL_PASSWORD")
DB_NAME = os.environ.get("CLOUD_SQL_DATABASE_NAME")
PRIVATE_IP = os.environ.get("PRIVATE_IP")

connector = Connector()

def _get_db_connection(db_name: str) -> pg8000.dbapi.Connection:
    """Helper function to establish a database connection."""
    ip_type = IPTypes.PRIVATE if PRIVATE_IP == "True" else IPTypes.PUBLIC
    return connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASS,
        db=db_name,
        ip_type=ip_type,
    )

def create_database_if_not_exists():
    """Connects to the default 'postgres' db and creates the target DB if it doesn't exist."""
    try:
        initial_conn = _get_db_connection("postgres")
        initial_conn.autocommit = True
        cursor = initial_conn.cursor()
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE {DB_NAME}")
            logger.info(f"Database '{DB_NAME}' created successfully.")
        else:
            logger.info(f"Database '{DB_NAME}' already exists.")
        cursor.close()
        initial_conn.close()
    except Exception as e:
        logger.error(f"Error in create_database_if_not_exists: {e}", exc_info=True)
        raise

create_database_if_not_exists()

def getconn() -> pg8000.dbapi.Connection:
    """Establishes a connection to the application's Cloud SQL database."""
    try:
        return _get_db_connection(DB_NAME)
    except Exception as e:
        logger.error(f"Error connecting to database in getconn: {e}", exc_info=True)
        raise

engine = sqlalchemy.create_engine(
    "postgresql+pg8000://",
    creator=getconn,
    pool_recycle=1800,  # Recycle connections every 30 minutes
    pool_pre_ping=True,  # Enable pre-ping to test connections before use
    connect_args={"timeout": 30}, # Add a connection timeout
    pool_timeout=30 # Add a pool timeout
)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialize the database (create tables)
def init_db():
    """Creates database tables based on SQLAlchemy models."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables checked/created successfully via database.init_db().")
    except Exception as e:
        logger.error(f"Error in database.init_db() creating tables: {e}", exc_info=True)
        # Depending on the severity, you might want to sys.exit or handle differently
