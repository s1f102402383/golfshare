FROM python:3.11
WORKDIR /app
RUN pip install django
# 「こういう環境を作ってね」という指示書