import os
import logging
import pymysql
from app import create_app, db
from app.models import User, Wordset, Word, UserWord, RecallHistory  # Importing necessary models
from google.cloud import storage
from dotenv import load_dotenv
from pathlib import Path
from sqlalchemy import text
from datetime import datetime  # For timestamp generation
import time
from flask.testing import FlaskClient
import werkzeug


# Load environment variables from the parent directory's .env file
env_path = Path('..') / '.env'
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class CustomFlaskClient(FlaskClient):
    def open(self, *args, **kwargs):
        kwargs.setdefault('headers', {})['User-Agent'] = 'Custom-Client/1.0'
        return super().open(*args, **kwargs)

class TestConfig:
    TESTING = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = ''  # Dynamically set in TestUtils

class TestUtils:

    @staticmethod
    def generate_temp_db_name():
        """
        Generates a unique temporary database name using the current timestamp.
        """
        timestamp = int(time.time())
        temp_db_name = f"test_db_{timestamp}"
        logger.debug(f"Generated temporary database name: {temp_db_name}")
        return temp_db_name

    @staticmethod
    def download_sql_script():
        """
        Download the SQL schema script from GCP storage.
        """
        logger.debug("Downloading schema SQL script from GCP storage.")
        storage_client = storage.Client()
        bucket_name = os.getenv('MYSQL_FILES_BUCKET')

        if not bucket_name:
            logger.error("MYSQL_FILES_BUCKET environment variable is not set.")
            raise EnvironmentError("MYSQL_FILES_BUCKET environment variable is required.")

        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob('schema-tables.sql')
        sql_script_path = '/tmp/schema-tables.sql'
        blob.download_to_filename(sql_script_path)
        logger.debug(f"SQL script downloaded to {sql_script_path}")
        return sql_script_path

    @staticmethod
    def run_sql_script(sql_script_path, db_name):
        """
        Execute the SQL script to create necessary tables in the specified database.
        """
        logger.debug(f"Executing SQL script for database: {db_name}")
        
        connection = pymysql.connect(
            host='127.0.0.1',
            port=3306,
            user='root',
            password=os.getenv('DB_ROOT_PASSWORD'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )

        try:
            with connection.cursor() as cursor:
                # Create the database if it doesn't exist and switch to it
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name};")
                cursor.execute(f"USE {db_name};")

                # Read and execute the SQL script
                with open(sql_script_path, 'r') as f:
                    sql_script = f.read()
                
                sql_commands = sql_script.split(';')

                for command in sql_commands:
                    if command.strip():  # Skip empty commands
                        cursor.execute(command.strip())

            logger.debug(f"SQL script executed successfully for database: {db_name}")
        except pymysql.MySQLError as e:
            logger.error(f"Error executing SQL script: {e}")
            raise
        finally:
            connection.close()

    @staticmethod
    def setup_test_app():
        """
        Creates and configures the Flask app and initializes the MySQL database for testing.
        Returns the Flask test client, the app instance, and the temporary database name.
        """
        # Monkey-patch werkzeug.__version__ to avoid the warning
        werkzeug.__version__ = "patched"

        temp_db_name = TestUtils.generate_temp_db_name()

        # Set the dynamic MySQL database URL
        TestConfig.SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://root:{os.getenv("DB_ROOT_PASSWORD")}@127.0.0.1:3306/{temp_db_name}'

        # Create the Flask app with the test configuration
        app = create_app(config_class=TestConfig)
        app.test_client_class = CustomFlaskClient  # Use custom client to suppress Werkzeug version warning
        client = app.test_client()

        # Disable object expiration after commit
        # db.session.configure(expire_on_commit=False)

        logger.debug(f"Database URI for testing: {TestConfig.SQLALCHEMY_DATABASE_URI}")

        # Initialize the database
        with app.app_context():
            logger.debug(f"Initializing database: {temp_db_name}")
            sql_script_path = TestUtils.download_sql_script()
            TestUtils.run_sql_script(sql_script_path, temp_db_name)

        return client, app, temp_db_name

    @staticmethod
    def teardown_test_db(app, temp_db_name):
        """
        Drops the temporary database after the tests are finished.
        """
        logger.debug(f"Dropping temporary database: {temp_db_name}")
        connection = pymysql.connect(
            host='127.0.0.1',
            port=3306,
            user='root',
            password=os.getenv('DB_ROOT_PASSWORD'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS {temp_db_name};")
                connection.commit()
            logger.debug(f"Temporary database {temp_db_name} dropped successfully.")
        except pymysql.MySQLError as e:
            logger.error(f"Error dropping database {temp_db_name}: {e}")
            raise
        finally:
            connection.close()

    @staticmethod
    def clear_database(db):
        """
        Clears all the relevant tables in the database before each test.
        """
        logger.debug("Clearing all tables before running the test.")
        try:
            db.session.query(RecallHistory).delete()
            db.session.query(UserWord).delete()
            db.session.query(Word).delete()
            db.session.query(Wordset).delete()
            db.session.query(User).delete()
            db.session.commit()
        except Exception as e:
            logger.error(f"Error clearing database: {e}")
            db.session.rollback()
            raise

    @staticmethod
    def create_test_word(db, user_email='test@example.com', word_description='Test Wordset', word_name=None):
        """
        Create a test user, wordset, and word entry.
        """
        # Create and add user and wordset
        user = User(email=user_email)
        db.session.add(user)
        db.session.commit()

        
        wordset = Wordset(description=word_description)
        db.session.add(wordset)
        db.session.commit()

        # Fetch wordset to ensure it's attached to the session and verify it
        wordset = db.session.query(Wordset).filter_by(description=word_description).first()
        if wordset is None:
            raise ValueError(f"Failed to retrieve wordset with description: {word_description}")


        # Create and add word
        if word_name is None:
            word_name = f'Test Word {datetime.utcnow().timestamp()}'

        word = Word(
            word=word_name,
            wordset_id=wordset.wordset_id,
            def1='Definition 1',
            def2='Definition 2'
        )
        db.session.add(word)
        db.session.commit()

        # Re-fetch user, wordset, and word to ensure they're attached to the session and verify them
        user = db.session.query(User).filter_by(email=user.email).first()
        if user is None:
            raise ValueError(f"Failed to retrieve user with email: {user_email}")

        wordset = db.session.query(Wordset).filter_by(wordset_id=wordset.wordset_id).first()
        if wordset is None:
            raise ValueError(f"Failed to retrieve wordset with description: {word_description}")

        word = db.session.query(Word).filter_by(word_id=word.word_id).first()
        if word is None:
            raise ValueError(f"Failed to retrieve word with name: {word_name}")

        return user, wordset, word


    @staticmethod
    def create_test_userword(db, user_email='test@example.com', word_description='Test Wordset', word_name=None):
        """
        Create a test user, wordset, word, and userword entry.
        """
        # Use the create_test_word method to create user, wordset, and word
        user, wordset, word = TestUtils.create_test_word(db, user_email, word_description, word_name)

        # Create and add userword
        userword = UserWord(user_id=user.email, word_id=word.word_id, is_included=True, recall_state=1)
        db.session.add(userword)
        db.session.commit()

        # Re-fetch userword to ensure it's attached to the session
        userword = db.session.query(UserWord).filter_by(user_id=user.email, word_id=word.word_id).first()

        return user, wordset, word, userword


