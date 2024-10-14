# Project Name

TaskFlow App

## Overview

This project is a Python application that utilizes AWS CDK for infrastructure as code. The project structure includes a main application file, AWS Lambda functions, and necessary configurations for deployment.

## Project Structure

- **app.py**: The main application file.
- **cdk.json**: Configuration file for AWS CDK.
- **cdk.out/**: Output directory for AWS CDK assets.
- **event.json**: Sample event data for testing.
- **lambda/**: Directory containing AWS Lambda function code.
- **lib/**: Directory for additional libraries or modules.
- **README.md**: Project documentation.
- **requirements.txt**: Python dependencies.
- **template.yml**: AWS CloudFormation template.
- **venv/**: Python virtual environment.

## Setup

1. **Clone the repository:**

   ```sh
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Create and activate a virtual environment:**

   ```sh
   python3 -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

## Deploying with AWS CDK

### Bootstrap your AWS environment (if not already done):

```
cdk bootstrap
```

### Deploy the stack:

```
cdk deploy
```
