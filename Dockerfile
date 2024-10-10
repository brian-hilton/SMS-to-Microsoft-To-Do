FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
EXPOSE 5000
ENV PYTHONUNBUFFERED=1
CMD ["python3", "main.py"]