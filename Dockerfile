# Use an official lightweight Python image.
FROM python:3.9-alpine

# Set the working directory.
WORKDIR /app

# Copy the requirements file and install dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . .

# Expose port 80
EXPOSE 80

# Set environment variable for Flask.
ENV FLASK_APP=app.py

# Run the Flask application.
CMD ["flask", "run", "--host=0.0.0.0", "--port 80"]
