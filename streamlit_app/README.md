# Telecom Churn Prediction — Streamlit App

## Quick Start

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

Open your browser at: `http://localhost:8501`

## Features
- **Single Prediction**: Enter customer details and get instant churn probability
- **Batch Prediction**: Upload a CSV file and get predictions for all customers  
- **Model Insights**: View model performance metrics and feature importances
- **Auto-compute**: Derived features (tenure, ratios, usage_score) computed automatically

## Usage

### Single Prediction
1. Navigate to "Single Prediction" in the sidebar
2. Fill in the three tabs: Demographics, Usage, Location
3. Click "Predict Churn"
4. View risk gauge, probability, and recommendations

### Batch Prediction
1. Navigate to "Batch Prediction"
2. Upload a CSV file with columns matching the raw dataset format
3. View predictions table with color-coded risk levels
4. Download results CSV

### Model Insights  
- View full model performance metrics
- Explore feature importance rankings
- Understand threshold optimization

## Requirements
- Python 3.9+
- The trained model at `../telecom_churn_pipeline.joblib`
- See `requirements.txt` for all dependencies
