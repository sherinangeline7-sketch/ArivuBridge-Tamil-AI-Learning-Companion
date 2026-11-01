# ArivuBridge – Tamil AI Learning Companion

**Learn Better. Understand Clearly. Get Guidance in Tamil and English.**

ArivuBridge is an AI-powered learning companion designed to help students access educational guidance in both Tamil and English. It aims to make learning support more accessible through Tamil-language understanding, curated educational resources, and responsible AI responses.

## 🎯 Project Overview

Many students find it difficult to access learning resources in their preferred language. ArivuBridge addresses this challenge by supporting Tamil and English queries and connecting students with relevant educational guidance.

The project uses the Strands Agents SDK and Amazon Bedrock to build an AI-powered assistant with a focus on relevant responses, language accessibility, and responsible student support.

## ✨ Key Features

- **Tamil and English Support:** Accepts queries in Tamil and English.
- **Tamil Script Detection:** Identifies Tamil-script input.
- **Bilingual Keyword Expansion:** Expands Tamil queries into relevant English keywords to improve guidance retrieval.
- **Curated Learning Guidance:** Uses a structured guidance knowledge base.
- **Relevant Results:** Ranks retrieved guidance by relevance and avoids unrelated fallback results.
- **Responsible Responses:** Designed to provide appropriate guidance for sensitive student situations.
- **Evaluation Support:** Includes test cases covering Tamil, English, emergency-related, and job-related scenarios.

## 🛠️ Technologies Used

- Python
- Strands Agents SDK
- Amazon Bedrock
- AWS Boto3
- Pydantic
- JSON-based guidance data

## 🏗️ Project Structure

```text
ArivuBridge/
│
├── agent/
│   ├── app.py
│   ├── plan.py
│   ├── tools.py
│   ├── score.py
│   ├── baseline.py
│   └── data/
│       └── guidance.json
│
├── ship_kit/
├── results/
├── article/
├── cases.jsonl
├── requirements.txt
├── DESIGN.md
├── FAILURES.md
├── IDEA.md
└── README.md
```

## ⚙️ Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/sherinangeline7-sketch/ArivuBridge-Tamil-AI-Learning-Companion.git
cd ArivuBridge-Tamil-AI-Learning-Companion
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the environment

**Windows PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

### 4. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## ☁️ Amazon Bedrock Configuration

ArivuBridge uses the Strands Agents SDK with Amazon Bedrock.

Configure AWS credentials using an approved AWS authentication method. Ensure that:

- Your AWS account has access to Amazon Bedrock.
- The selected foundation model is enabled and available in your AWS region.
- Your IAM permissions allow the required Bedrock model invocation.

The application supports these environment variables:

| Variable | Purpose |
|---|---|
| `SHIP_MODEL` | Selects the Bedrock model |
| `AWS_REGION` | Sets the AWS region |
| `SHIP_JUDGE_MODEL` | Selects the evaluation judge model |

Default model: `us.amazon.nova-2-lite-v1:0`

Default region: `us-east-1`

## 🧪 Testing and Evaluation

The project includes an evaluation dataset with 37 test cases:

- 16 Tamil-language cases
- 21 English-language cases
- Coverage for emergency-related and job-related scenarios

The evaluation process is intended to assess language understanding, relevance of retrieved guidance, and response quality.

## 🌱 Project Goals

- Make AI-powered learning support more accessible to Tamil-speaking students.
- Reduce language barriers in accessing educational guidance.
- Improve the relevance of information retrieved for student questions.
- Encourage responsible and student-friendly AI assistance.

## 🔮 Future Enhancements

- Voice-based Tamil learning assistance.
- Improved conversational learning support.
- Expanded subject-wise educational resources.
- Personalized learning recommendations.
- Additional evaluation and accessibility improvements.

## 👩‍💻 Author

**Sherin Angeline A**

Project: **ArivuBridge – Tamil AI Learning Companion**

## 📌 Note

ArivuBridge is an educational support project. Its responses are intended as guidance and should not be treated as official institutional, emergency, or professional advice.

---

**ArivuBridge – Making Learning More Accessible Through AI and Tamil.**
