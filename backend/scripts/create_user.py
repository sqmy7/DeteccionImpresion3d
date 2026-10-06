import asyncio
import sys

from app.core.security import hash_password
from app.db.models import User, UserRole
from app.db.session import async_session_factory


async def main(username: str, email: str, password: str, role: str) -> None:
    async with async_session_factory() as session:
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role=UserRole(role),
        )
        session.add(user)
        await session.commit()
        print(f"Created user '{username}' (id={user.id}, role={user.role.value})")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python -m scripts.create_user <username> <email> <password> <admin|viewer>")
        sys.exit(1)
    asyncio.run(main(*sys.argv[1:]))
