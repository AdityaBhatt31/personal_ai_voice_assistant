from pathlib import Path
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "dataset" / "intents.csv"
MODEL_DIR = BASE_DIR / "model"
MODEL_FILE = MODEL_DIR / "intent_model.pkl"

def train():
    df = pd.read_csv(DATA_FILE)
    if df.empty or not {"text", "intent"}.issubset(df.columns):
        raise ValueError("Dataset must contain 'text' and 'intent' columns.")
    df = df.dropna(subset=["text", "intent"])
    df["text"] = df["text"].astype(str).str.strip()
    df["intent"] = df["intent"].astype(str).str.strip()
    df = df[df["text"].ne("")].drop_duplicates(subset="text", keep="first")
    counts = df["intent"].value_counts()
    if (counts < 5).any():
        raise ValueError(f"Need at least 5 examples per intent; got {counts[counts < 5].to_dict()}")

    features = FeatureUnion([
        ("words", TfidfVectorizer(lowercase=True, strip_accents="unicode",
                                   ngram_range=(1, 2), sublinear_tf=True)),
        ("characters", TfidfVectorizer(lowercase=True, strip_accents="unicode",
                                        analyzer="char_wb", ngram_range=(3, 5),
                                        min_df=1, sublinear_tf=True)),
    ])

    def make_model():
        return Pipeline([
            ("features", features),
            ("classifier", LogisticRegression(max_iter=2500, C=3, class_weight="balanced")),
        ])

    x_train, x_valid, y_train, y_valid = train_test_split(
        df["text"], df["intent"], test_size=0.2, random_state=42, stratify=df["intent"]
    )
    validation_model = make_model().fit(x_train, y_train)
    predictions = validation_model.predict(x_valid)
    print(f"Held-out accuracy: {accuracy_score(y_valid, predictions):.1%}")

    pipeline = make_model()

    pipeline.fit(df["text"], df["intent"])
    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(pipeline, MODEL_FILE)

    print(f"Model trained successfully.")
    print(f"Classes: {sorted(df['intent'].unique())}")
    print(f"Saved to: {MODEL_FILE}")

if __name__ == "__main__":
    train()
