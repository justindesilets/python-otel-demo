FROM python:3.14-slim-trixie

WORKDIR /usr/src/app

COPY ./app/requirements.txt /usr/src/requirements.txt
RUN pip install --no-cache-dir -r /usr/src/requirements.txt

COPY ./app /usr/src/app

CMD ["fastapi", "dev", "main.py", "--port", "8080", "--host", "0.0.0.0"]
