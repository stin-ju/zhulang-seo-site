from jc_db import connect, Connection, Cursor

class Error(Exception): pass
class DatabaseError(Error): pass
class OperationalError(DatabaseError): pass
class InterfaceError(DatabaseError): pass
class DataError(DatabaseError): pass
class IntegrityError(DatabaseError): pass
class InternalError(DatabaseError): pass
class ProgrammingError(DatabaseError): pass
class NotSupportedError(DatabaseError): pass

class extras: pass

class extensions:
    ISOLATION_LEVEL_AUTOCOMMIT = 0
