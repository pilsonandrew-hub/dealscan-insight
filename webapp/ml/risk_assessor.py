"""
Risk Assessment Model for Vehicle Opportunities
"""
import pickle
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from pathlib import Path
from datetime import datetime

from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler

from config.settings import settings
from webapp.database import SessionLocal
from webapp.models.vehicle import Vehicle, MLModel

class RiskAssessor:
    """Assess risk factors for vehicle purchases"""
    
    def __init__(self):
        self.model = None
        self.anomaly_detector = None
        self.label_encoders = {}
        self.scaler = StandardScaler()
        self.feature_columns = [
            'make', 'model', 'year', 'mileage', 'state', 'title_status',
            'age', 'mileage_per_year', 'price_per_mile'
        ]
        self.model_version = "1.0.0"
        
        # Risk factor definitions
        self.risk_factors = {
            'high_mileage': {'threshold': 150000, 'weight': 0.3},
            'old_vehicle': {'threshold': 15, 'weight': 0.2},
            'salvage_title': {'weight': 0.5},
            'flood_damage': {'weight': 0.4},
            'accident_history': {'weight': 0.3},
            'unknown_history': {'weight': 0.2},
            'remote_location': {'weight': 0.1},
            'unusual_price': {'weight': 0.3}
        }
    
    async def assess(self, vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess risk for a vehicle"""
        
        # Calculate individual risk factors
        risk_factors = []
        total_risk = 0.0
        
        # High mileage risk
        mileage = vehicle_data.get('mileage', 0)
        if mileage > self.risk_factors['high_mileage']['threshold']:
            risk_factors.append('high_mileage')
            total_risk += self.risk_factors['high_mileage']['weight']
        
        # Age risk
        year = vehicle_data.get('year', datetime.now().year)
        age = datetime.now().year - year
        if age > self.risk_factors['old_vehicle']['threshold']:
            risk_factors.append('old_vehicle')
            total_risk += self.risk_factors['old_vehicle']['weight']
        
        # Title status risk
        title_status = vehicle_data.get('title_status', 'clean').lower()
        if title_status in ['salvage', 'rebuilt', 'flood']:
            risk_factors.append(f'{title_status}_title')
            if title_status == 'salvage':
                total_risk += self.risk_factors['salvage_title']['weight']
            elif title_status == 'flood':
                total_risk += self.risk_factors['flood_damage']['weight']
        
        # Unknown history risk
        if not vehicle_data.get('vin') or len(str(vehicle_data.get('vin', ''))) != 17:
            risk_factors.append('unknown_history')
            total_risk += self.risk_factors['unknown_history']['weight']
        
        # Remote location risk (simplified)
        state = vehicle_data.get('state', '').lower()
        remote_states = ['ak', 'hi', 'mt', 'wy', 'nd', 'sd']
        if state in remote_states:
            risk_factors.append('remote_location')
            total_risk += self.risk_factors['remote_location']['weight']
        
        # Anomaly detection if model available
        if self.anomaly_detector:
            anomaly_score = await self._detect_anomaly(vehicle_data)
            if anomaly_score < -0.5:  # Threshold for anomaly
                risk_factors.append('unusual_pattern')
                total_risk += self.risk_factors['unusual_price']['weight']
        
        # Normalize risk score to 0-1 range
        risk_score = min(total_risk, 1.0)
        
        # Risk level categorization
        if risk_score < 0.3:
            risk_level = 'low'
        elif risk_score < 0.6:
            risk_level = 'medium'
        else:
            risk_level = 'high'
        
        return {
            'risk_score': risk_score,
            'risk_level': risk_level,
            'risk_factors': risk_factors,
            'detailed_risks': self._get_detailed_risks(risk_factors, vehicle_data),
            'recommendations': self._get_recommendations(risk_factors, risk_level)
        }
    
    def _get_detailed_risks(self, risk_factors: List[str], vehicle_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get detailed risk explanations"""
        detailed = []
        
        for factor in risk_factors:
            if factor == 'high_mileage':
                detailed.append({
                    'type': 'high_mileage',
                    'description': f"High mileage ({vehicle_data.get('mileage', 0):,} miles)",
                    'impact': 'Increased maintenance costs and reliability concerns',
                    'mitigation': 'Thorough mechanical inspection recommended'
                })
            elif factor == 'old_vehicle':
                year = vehicle_data.get('year', datetime.now().year)
                age = datetime.now().year - year
                detailed.append({
                    'type': 'old_vehicle',
                    'description': f"Older vehicle ({age} years old)",
                    'impact': 'Higher likelihood of mechanical issues and parts availability',
                    'mitigation': 'Research common issues for this model year'
                })
            elif 'title' in factor:
                detailed.append({
                    'type': 'title_issue',
                    'description': f"Title status: {vehicle_data.get('title_status', 'unknown')}",
                    'impact': 'Reduced resale value and potential insurance issues',
                    'mitigation': 'Factor into resale price calculations'
                })
            elif factor == 'unknown_history':
                detailed.append({
                    'type': 'unknown_history',
                    'description': 'Limited vehicle history information',
                    'impact': 'Unknown maintenance and accident history',
                    'mitigation': 'Request detailed vehicle history report'
                })
            elif factor == 'remote_location':
                detailed.append({
                    'type': 'remote_location',
                    'description': f"Located in {vehicle_data.get('state', 'unknown')}",
                    'impact': 'Higher transportation costs',
                    'mitigation': 'Factor transportation costs into bid calculation'
                })
        
        return detailed
    
    def _get_recommendations(self, risk_factors: List[str], risk_level: str) -> List[str]:
        """Get risk mitigation recommendations"""
        recommendations = []
        
        if risk_level == 'high':
            recommendations.append("Consider skipping this opportunity due to high risk")
            recommendations.append("If proceeding, significantly reduce bid amount")
        elif risk_level == 'medium':
            recommendations.append("Proceed with caution and thorough inspection")
            recommendations.append("Adjust profit margins to account for risks")
        
        if 'high_mileage' in risk_factors:
            recommendations.append("Budget extra for maintenance and repairs")
            
        if any('title' in factor for factor in risk_factors):
            recommendations.append("Research insurance and financing requirements")
            recommendations.append("Adjust resale value expectations")
            
        if 'unknown_history' in risk_factors:
            recommendations.append("Request comprehensive vehicle history report")
            recommendations.append("Plan for detailed pre-purchase inspection")
        
        return recommendations
    
    async def _detect_anomaly(self, vehicle_data: Dict[str, Any]) -> float:
        """Detect if vehicle data is anomalous"""
        try:
            if not self.anomaly_detector:
                return 0.0
            
            # Prepare features for anomaly detection
            df = pd.DataFrame([vehicle_data])
            X = self._prepare_features(df)
            
            # Get anomaly score
            score = self.anomaly_detector.decision_function(X)[0]
            return float(score)
            
        except Exception:
            return 0.0
    
    def _prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """Prepare features for model"""
        df = df.copy()
        
        # Feature engineering
        df['age'] = 2024 - df.get('year', 2020)
        df['mileage_per_year'] = df.get('mileage', 0) / np.maximum(df['age'], 1)
        df['price_per_mile'] = df.get('current_bid', 0) / np.maximum(df.get('mileage', 1), 1)
        
        # Encode categorical variables
        for col in ['make', 'model', 'state', 'title_status']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.lower()
                if col in self.label_encoders:
                    # Handle unseen categories
                    mask = df[col].isin(self.label_encoders[col].classes_)
                    df.loc[~mask, col] = 'unknown'
                    df[col] = self.label_encoders[col].transform(df[col])
                else:
                    # For new categorical data, use simple encoding
                    df[col] = pd.Categorical(df[col]).codes
        
        # Select features
        available_features = [col for col in self.feature_columns if col in df.columns]
        feature_df = df[available_features]
        
        # Fill missing values
        feature_df = feature_df.fillna(0)
        
        return feature_df.values
    
    async def retrain(self):
        """Retrain risk assessment models"""
        try:
            print("Starting risk model retraining...")
            
            # Get training data
            db = SessionLocal()
            vehicles = db.query(Vehicle).filter(
                Vehicle.current_bid.isnot(None),
                Vehicle.make.isnot(None),
                Vehicle.model.isnot(None)
            ).all()
            db.close()
            
            if len(vehicles) < 50:
                print("Insufficient data for risk model training")
                return
            
            # Prepare data
            data = []
            for vehicle in vehicles:
                data.append({
                    'make': vehicle.make or 'unknown',
                    'model': vehicle.model or 'unknown',
                    'year': vehicle.year or 2020,
                    'mileage': vehicle.mileage or 0,
                    'state': vehicle.state or 'unknown',
                    'title_status': vehicle.title_status or 'clean',
                    'current_bid': vehicle.current_bid or 0
                })
            
            df = pd.DataFrame(data)
            
            # Train anomaly detection model
            X = self._prepare_features(df)
            
            self.anomaly_detector = IsolationForest(
                contamination=0.1,
                random_state=42,
                n_estimators=100
            )
            
            self.anomaly_detector.fit(X)
            
            # Save model
            model_data = {
                'anomaly_detector': self.anomaly_detector,
                'label_encoders': self.label_encoders,
                'scaler': self.scaler,
                'version': self.model_version,
                'trained_at': datetime.now().isoformat()
            }
            
            model_path = Path(settings.ml_model_path) / "risk_assessor.pkl"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(model_path, 'wb') as f:
                pickle.dump(model_data, f)
            
            print("Risk assessment model retrained successfully")
            
        except Exception as e:
            print(f"Risk model retraining failed: {e}")
    
    async def get_feature_importance(self) -> List[Dict[str, Any]]:
        """Get risk factor importance"""
        factors = []
        for factor, config in self.risk_factors.items():
            factors.append({
                'feature': factor,
                'importance': config['weight'],
                'description': factor.replace('_', ' ').title()
            })
        
        factors.sort(key=lambda x: x['importance'], reverse=True)
        return factors