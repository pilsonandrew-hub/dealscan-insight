"""
ML Price Prediction Model with SHAP explanations
"""
import pickle
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
import joblib
from datetime import datetime
import asyncio
from pathlib import Path

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
import shap

from config.settings import settings
from webapp.database import SessionLocal
from webapp.models.vehicle import Vehicle, MLModel

class PricePredictor:
    """Vehicle price prediction with explainability"""
    
    def __init__(self):
        self.model = None
        self.label_encoders = {}
        self.scaler = StandardScaler()
        self.feature_columns = [
            'make', 'model', 'year', 'mileage', 'state', 'condition',
            'title_status', 'age', 'mileage_per_year'
        ]
        self.model_version = "1.0.0"
        self.explainer = None
        
        # Load model if exists
        asyncio.create_task(self.load_model())
    
    async def load_model(self):
        """Load trained model from disk"""
        try:
            model_path = Path(settings.ml_model_path) / "price_predictor.pkl"
            if model_path.exists():
                with open(model_path, 'rb') as f:
                    model_data = pickle.load(f)
                    self.model = model_data['model']
                    self.label_encoders = model_data['label_encoders']
                    self.scaler = model_data['scaler']
                    self.model_version = model_data.get('version', '1.0.0')
                    
                # Initialize SHAP explainer
                if self.model:
                    # Use a sample of training data for TreeExplainer
                    sample_data = self._create_sample_data()
                    self.explainer = shap.TreeExplainer(self.model, sample_data)
                    
                print(f"Loaded price prediction model v{self.model_version}")
            else:
                print("No trained model found. Training new model...")
                await self.retrain()
                
        except Exception as e:
            print(f"Failed to load price model: {e}")
            # Initialize with default model
            self.model = RandomForestRegressor(n_estimators=100, random_state=42)
    
    def _create_sample_data(self) -> np.ndarray:
        """Create sample data for SHAP explainer"""
        # Create synthetic sample data with proper feature engineering
        sample_size = 100
        np.random.seed(42)
        
        makes = ['ford', 'chevrolet', 'dodge', 'toyota', 'honda']
        models = ['f150', 'silverado', 'ram', 'camry', 'accord']
        states = ['ca', 'tx', 'fl', 'ny', 'pa']
        conditions = ['excellent', 'good', 'fair', 'poor']
        
        sample_data = []
        for _ in range(sample_size):
            data = {
                'make': np.random.choice(makes),
                'model': np.random.choice(models),
                'year': np.random.randint(2000, 2024),
                'mileage': np.random.randint(0, 200000),
                'state': np.random.choice(states),
                'condition': np.random.choice(conditions),
                'title_status': 'clean'
            }
            data['age'] = 2024 - data['year']
            data['mileage_per_year'] = data['mileage'] / max(data['age'], 1)
            
            sample_data.append(data)
        
        df = pd.DataFrame(sample_data)
        return self._prepare_features(df)
    
    def _prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """Prepare features for model prediction"""
        df = df.copy()
        
        # Feature engineering
        df['age'] = 2024 - df['year']
        df['mileage_per_year'] = df['mileage'] / np.maximum(df['age'], 1)
        
        # Encode categorical variables
        for col in ['make', 'model', 'state', 'condition', 'title_status']:
            if col in df.columns:
                if col in self.label_encoders:
                    # Handle unseen categories
                    df[col] = df[col].astype(str).str.lower()
                    mask = df[col].isin(self.label_encoders[col].classes_)
                    df.loc[~mask, col] = 'unknown'
                    
                    # Add 'unknown' class if not present
                    if 'unknown' not in self.label_encoders[col].classes_:
                        # Create new encoder with unknown class
                        all_classes = list(self.label_encoders[col].classes_) + ['unknown']
                        self.label_encoders[col].classes_ = np.array(all_classes)
                    
                    df[col] = self.label_encoders[col].transform(df[col])
                else:
                    # Create new encoder
                    self.label_encoders[col] = LabelEncoder()
                    df[col] = df[col].astype(str).str.lower()
                    df[col] = self.label_encoders[col].fit_transform(df[col])
        
        # Select and order features
        feature_df = df[self.feature_columns]
        
        # Scale numerical features
        if hasattr(self.scaler, 'mean_'):
            return self.scaler.transform(feature_df)
        else:
            return self.scaler.fit_transform(feature_df)
    
    async def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict vehicle price"""
        if not self.model:
            raise ValueError("Model not trained")
        
        # Convert to DataFrame
        df = pd.DataFrame([features])
        
        # Prepare features
        X = self._prepare_features(df)
        
        # Make prediction
        prediction = self.model.predict(X)[0]
        
        # Calculate confidence based on prediction interval
        confidence = self._calculate_confidence(X)
        
        # Calculate price range (confidence interval)
        price_range = self._calculate_price_range(X, prediction)
        
        # Get feature importance explanation
        factors = await self._explain_prediction(X)
        
        return {
            "predicted_price": float(prediction),
            "confidence": float(confidence),
            "price_range": price_range,
            "factors": factors,
            "model_version": self.model_version
        }
    
    def _calculate_confidence(self, X: np.ndarray) -> float:
        """Calculate prediction confidence"""
        if hasattr(self.model, 'predict_proba'):
            # For classifiers
            probas = self.model.predict_proba(X)
            return float(np.max(probas[0]))
        else:
            # For regressors, use a heuristic based on training performance
            # This is simplified - in production, use proper uncertainty quantification
            return 0.85  # Default confidence
    
    def _calculate_price_range(self, X: np.ndarray, prediction: float) -> Dict[str, float]:
        """Calculate price confidence interval"""
        # Simplified approach - use percentage of prediction
        # In production, use proper prediction intervals
        uncertainty = prediction * 0.15  # 15% uncertainty
        
        return {
            "low": max(0, prediction - uncertainty),
            "high": prediction + uncertainty
        }
    
    async def _explain_prediction(self, X: np.ndarray) -> List[Dict[str, Any]]:
        """Explain prediction using SHAP"""
        try:
            if self.explainer is None:
                return [{"feature": "model_not_available", "impact": 0, "value": "N/A"}]
            
            # Get SHAP values
            shap_values = self.explainer.shap_values(X)
            
            # Create explanation
            factors = []
            for i, feature_name in enumerate(self.feature_columns):
                impact = float(shap_values[0][i])
                value = float(X[0][i])
                
                factors.append({
                    "feature": feature_name,
                    "impact": impact,
                    "value": value,
                    "importance": abs(impact)
                })
            
            # Sort by importance
            factors.sort(key=lambda x: x["importance"], reverse=True)
            
            return factors[:5]  # Return top 5 factors
            
        except Exception as e:
            print(f"SHAP explanation failed: {e}")
            return [{"feature": "explanation_error", "impact": 0, "value": str(e)}]
    
    async def retrain(self):
        """Retrain the model with latest data"""
        try:
            print("Starting price model retraining...")
            
            # Get training data
            db = SessionLocal()
            
            # Query vehicles with price data
            vehicles = db.query(Vehicle).filter(
                Vehicle.current_bid.isnot(None),
                Vehicle.current_bid > 0,
                Vehicle.make.isnot(None),
                Vehicle.model.isnot(None),
                Vehicle.year.isnot(None)
            ).all()
            
            db.close()
            
            if len(vehicles) < 100:
                print("Insufficient training data")
                return
            
            # Prepare training data
            data = []
            for vehicle in vehicles:
                data.append({
                    'make': vehicle.make or 'unknown',
                    'model': vehicle.model or 'unknown',
                    'year': vehicle.year or 2020,
                    'mileage': vehicle.mileage or 0,
                    'state': vehicle.state or 'unknown',
                    'condition': 'good',  # Default
                    'title_status': vehicle.title_status or 'clean',
                    'price': vehicle.current_bid
                })
            
            df = pd.DataFrame(data)
            
            # Feature engineering
            df['age'] = 2024 - df['year']
            df['mileage_per_year'] = df['mileage'] / np.maximum(df['age'], 1)
            
            # Prepare features and target
            y = df['price'].values
            X = self._prepare_features(df.drop('price', axis=1))
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Train model
            self.model = RandomForestRegressor(
                n_estimators=200,
                max_depth=20,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1
            )
            
            self.model.fit(X_train, y_train)
            
            # Evaluate model
            y_pred = self.model.predict(X_test)
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            
            print(f"Model performance - MAE: {mae:.2f}, R2: {r2:.3f}")
            
            # Initialize SHAP explainer
            self.explainer = shap.TreeExplainer(self.model, X_train[:100])
            
            # Save model
            model_data = {
                'model': self.model,
                'label_encoders': self.label_encoders,
                'scaler': self.scaler,
                'version': self.model_version,
                'performance': {'mae': mae, 'r2': r2},
                'trained_at': datetime.now().isoformat()
            }
            
            model_path = Path(settings.ml_model_path) / "price_predictor.pkl"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(model_path, 'wb') as f:
                pickle.dump(model_data, f)
            
            # Update database
            db = SessionLocal()
            ml_model = db.query(MLModel).filter(
                MLModel.name == "price_predictor"
            ).first()
            
            if not ml_model:
                ml_model = MLModel(
                    name="price_predictor",
                    model_type="regressor"
                )
                db.add(ml_model)
            
            ml_model.version = self.model_version
            ml_model.features = self.feature_columns
            ml_model.performance_metrics = {'mae': mae, 'r2': r2}
            ml_model.model_path = str(model_path)
            ml_model.is_active = True
            ml_model.is_production = True
            ml_model.trained_at = datetime.now()
            
            db.commit()
            db.close()
            
            print(f"Price model retrained successfully (v{self.model_version})")
            
        except Exception as e:
            print(f"Model retraining failed: {e}")
            raise
    
    async def get_feature_importance(self) -> List[Dict[str, Any]]:
        """Get feature importance from trained model"""
        if not self.model:
            return []
        
        if hasattr(self.model, 'feature_importances_'):
            importance = self.model.feature_importances_
            
            features = []
            for i, feature_name in enumerate(self.feature_columns):
                features.append({
                    "feature": feature_name,
                    "importance": float(importance[i])
                })
            
            features.sort(key=lambda x: x["importance"], reverse=True)
            return features
        
        return []
    
    async def explain_prediction(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed explanation for a specific prediction"""
        df = pd.DataFrame([features])
        X = self._prepare_features(df)
        
        explanation = await self._explain_prediction(X)
        prediction = self.model.predict(X)[0] if self.model else 0
        
        return {
            "prediction": float(prediction),
            "factors": explanation,
            "model_version": self.model_version,
            "features_used": self.feature_columns
        }