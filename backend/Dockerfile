FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY saving_tracker.py db.py auth.py notify.py .

ENV PORT=8000
ENV NO_BROWSER=1

EXPOSE 8000

CMD ["python3", "saving_tracker.py"]
