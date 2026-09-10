import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, default="")
    image_url = Column(String(500), default="")
    is_active = Column(Boolean, default=True)

    questions = relationship("Question", back_populates="topic", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    text = Column(Text, nullable=False)
    image_url = Column(String(500), default="")
    option_a = Column(String(300), nullable=False)
    option_b = Column(String(300), nullable=False)
    option_c = Column(String(300), nullable=False)
    option_d = Column(String(300), nullable=False)
    correct_option = Column(String(1), nullable=False)  # A/B/C/D
    explanation = Column(Text, default="")
    difficulty = Column(Integer, default=1)  # 1, 2, or 3

    is_active = Column(Boolean, default=True)

    topic = relationship("Topic", back_populates="questions")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    avatar_url = Column(String(500), default="")
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    status = Column(String(20), default="waiting")  # waiting, active, finished
    current_question_index = Column(Integer, default=-1)
    questions_order = Column(Text, default="[]")  # JSON list of question IDs
    started_at = Column(DateTime, nullable=True)
    question_started_at = Column(DateTime, nullable=True)

    topic = relationship("Topic")

    def get_questions_order(self):
        return json.loads(self.questions_order) if self.questions_order else []

    def set_questions_order(self, ids):
        self.questions_order = json.dumps(ids)


class TeamAnswer(Base):
    __tablename__ = "team_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_option = Column(String(1), nullable=False)
    is_correct = Column(Boolean, default=False)
    answered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nickname = Column(String(100), nullable=False)
    email = Column(String(200), nullable=False, unique=True)
    password_hash = Column(String(200), nullable=False)
    total_score = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, default="")
    code = Column(String(10), nullable=False, unique=True)
    is_private = Column(Boolean, default=False)
    status = Column(String(20), default="waiting")  # waiting, active, finished
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    current_question_index = Column(Integer, default=-1)
    questions_order = Column(Text, default="[]")
    started_at = Column(DateTime, nullable=True)
    question_started_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    topic = relationship("Topic")

    def get_questions_order(self):
        return json.loads(self.questions_order) if self.questions_order else []

    def set_questions_order(self, ids):
        self.questions_order = json.dumps(ids)


class RoomMember(Base):
    __tablename__ = "room_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    nickname = Column(String(100), nullable=False)
    team = Column(String(10), nullable=False)  # 'A' or 'B'
    role = Column(String(20), nullable=False)  # 'player' or 'observer'
    score = Column(Integer, default=0)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RoomAnswer(Base):
    __tablename__ = "room_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    room_member_id = Column(Integer, ForeignKey("room_members.id"), nullable=False)
    team = Column(String(10), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_option = Column(String(1), nullable=False)
    is_correct = Column(Boolean, default=False)
    answered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SuggestedTopic(Base):
    __tablename__ = "suggested_topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    suggested_by = Column(String(100), nullable=False)
    player_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    votes = relationship("TopicVote", back_populates="suggested_topic", cascade="all, delete-orphan")


class TopicVote(Base):
    __tablename__ = "topic_votes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    suggested_topic_id = Column(Integer, ForeignKey("suggested_topics.id"), nullable=False)
    player_nickname = Column(String(100), nullable=False)
    vote = Column(Integer, nullable=False)  # +1 or -1
    voted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    suggested_topic = relationship("SuggestedTopic", back_populates="votes")


class VisitStats(Base):
    __tablename__ = "visit_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page = Column(String(200), nullable=False)
    player_nickname = Column(String(100), nullable=True)
    visited_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    session_duration = Column(Integer, nullable=True)
