FROM python:3.10-slim

COPY . C:\app
WORKDIR C:\app

RUN python -m pip install --upgrade pip && \
    python setup.py

CMD ["python", "main.py"]
