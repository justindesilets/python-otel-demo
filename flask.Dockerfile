FROM python:3.14-slim-trixie

WORKDIR /usr/src/app

COPY ./flask_app/requirements.txt /usr/src/requirements.txt
RUN pip install --no-cache-dir -r /usr/src/requirements.txt

COPY ./flask_app /usr/src/app

CMD ["opentelemetry-instrument", "flask", "--app", "main.py", "run", "--port", "8081", "--host", "0.0.0.0"]
