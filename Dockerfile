FROM python:3.10-slim

# Корректные Linux-пути для slim-образа
WORKDIR /app
COPY . /app

ENV PYTHONUNBUFFERED=1

RUN python -m pip install --upgrade pip && \
    python setup.py

CMD ["python", "main.py"]
