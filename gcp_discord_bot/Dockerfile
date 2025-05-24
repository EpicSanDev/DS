FROM python:3.10-slim-buster
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /app/data
COPY ./src /app/src
COPY ./config /app/config
# Assurez-vous que bot.py est exécutable ou ajustez les permissions si nécessaire
# RUN chmod +x /app/src/bot.py
CMD ["python", "src/bot.py"]