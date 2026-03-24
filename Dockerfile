FROM python:3.11-slim
WORKDIR /src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# 這一行絕對不能少
ENV PYTHONPATH=/src
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]