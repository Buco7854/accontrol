FROM python:3.10-slim-buster

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["./entrypoint.sh"]

CMD ["gunicorn", "-w","4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:5000", "app:app"]