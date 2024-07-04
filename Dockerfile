# Stage 1: Build stage to generate the index.html file
FROM python:3.9-alpine AS builder

WORKDIR /app

COPY generate.py hub.ini requirements.txt /app/

RUN pip install -r requirements.txt

COPY templates/index_template.html /app/templates/index_template.html
COPY images/ /app/images/

# Run the script to generate index.html
RUN python generate.py

# Stage 2: Final stage to create the httpd container
FROM httpd:2.4-alpine

COPY --from=builder /app/index.html /usr/local/apache2/htdocs/index.html
COPY --from=builder /app/images/ /usr/local/apache2/htdocs/images/
