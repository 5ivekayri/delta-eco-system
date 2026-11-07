"""Create the initial administrator; password is read from stdin, never argv."""
import sys
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from delta_contracts.config import Settings
from .models import User
from .service import hash_password

def main():
    password=sys.stdin.readline().rstrip('\n')
    if len(password)<16:raise SystemExit('Password must have at least 16 characters')
    engine=create_engine(Settings().database_url)
    with Session(engine) as db:
        if db.scalar(select(User).where(User.username=='admin')):raise SystemExit('admin already exists; unchanged')
        db.add(User(username='admin',password_hash=hash_password(password),role='admin'));db.commit()
    print('Administrator created')
if __name__=='__main__':main()
