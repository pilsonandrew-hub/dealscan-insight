"""
Opportunity Scoring Model for Deal Ranking
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from datetime import datetime, timedelta

from webapp.ml.price_predictor import PricePredictor
from webapp.ml.risk_assessor import RiskAssessor

class OpportunityScorer:
    """Score and rank vehicle opportunities"""
    
    def __init__(self):
        self.price_predictor = PricePredictor()
        self.risk_assessor = RiskAssessor()
        self.model_version = "1.0.0"
        
        # Scoring weights
        self.weights = {
            'profit_margin': 0.4,      # Primary factor
            'roi_percentage': 0.3,      # Return on investment
            'confidence': 0.2,          # Price prediction confidence
            'risk_adjustment': -0.3,    # Risk penalty
            'time_factor': 0.1          # Time sensitivity
        }
    
    async def score(self, opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Score an opportunity"""
        
        vehicle_data = opportunity_data['vehicle']
        current_bid = opportunity_data['current_bid']
        fees = opportunity_data.get('fees', 0)
        transportation_cost = opportunity_data.get('transportation_cost', 0)
        
        # Get price prediction
        price_result = await self.price_predictor.predict(vehicle_data)
        predicted_retail = price_result['predicted_price']
        confidence = price_result['confidence']
        
        # Get risk assessment
        risk_result = await self.risk_assessor.assess(vehicle_data)
        risk_score = risk_result['risk_score']
        
        # Calculate costs and profits
        total_cost = current_bid + fees + transportation_cost
        potential_profit = predicted_retail - total_cost
        profit_margin = (potential_profit / predicted_retail) if predicted_retail > 0 else 0
        roi_percentage = (potential_profit / total_cost) if total_cost > 0 else 0
        
        # Time factor (auction ending soon gets bonus)
        time_factor = self._calculate_time_factor(opportunity_data)
        
        # Calculate composite score
        score_components = {
            'profit_margin_score': self._normalize_profit_margin(profit_margin),
            'roi_score': self._normalize_roi(roi_percentage),
            'confidence_score': confidence,
            'risk_penalty': risk_score,
            'time_bonus': time_factor
        }
        
        # Weighted composite score
        composite_score = (
            score_components['profit_margin_score'] * self.weights['profit_margin'] +
            score_components['roi_score'] * self.weights['roi_percentage'] +
            score_components['confidence_score'] * self.weights['confidence'] +
            score_components['risk_penalty'] * self.weights['risk_adjustment'] +
            score_components['time_bonus'] * self.weights['time_factor']
        )
        
        # Normalize to 0-1 range
        final_score = max(0, min(1, composite_score))
        
        # Generate recommendation
        recommendation = self._generate_recommendation(
            final_score, profit_margin, roi_percentage, risk_score
        )
        
        # Estimate days to sell
        days_to_sell = self._estimate_days_to_sell(vehicle_data, profit_margin)
        
        return {
            'score': final_score,
            'potential_profit': potential_profit,
            'profit_margin': profit_margin * 100,  # Convert to percentage
            'roi_percentage': roi_percentage * 100,
            'predicted_retail_price': predicted_retail,
            'total_cost': total_cost,
            'confidence': confidence,
            'risk_score': risk_score,
            'recommendation': recommendation,
            'days_to_sell': days_to_sell,
            'factors': price_result['factors'],
            'score_breakdown': score_components,
            'model_version': self.model_version
        }
    
    def _normalize_profit_margin(self, margin: float) -> float:
        """Normalize profit margin to 0-1 score"""
        # Target margin: 20-30% = score 1.0
        # 10-20% = score 0.5-1.0
        # 0-10% = score 0-0.5
        # Negative = score 0
        
        if margin < 0:
            return 0.0
        elif margin < 0.1:  # 0-10%
            return margin * 5  # 0-0.5 score
        elif margin < 0.2:  # 10-20%
            return 0.5 + (margin - 0.1) * 5  # 0.5-1.0 score
        else:  # 20%+
            return 1.0
    
    def _normalize_roi(self, roi: float) -> float:
        """Normalize ROI to 0-1 score"""
        # Target ROI: 50%+ = score 1.0
        # 25-50% = score 0.5-1.0
        # 0-25% = score 0-0.5
        # Negative = score 0
        
        if roi < 0:
            return 0.0
        elif roi < 0.25:  # 0-25%
            return roi * 2  # 0-0.5 score
        elif roi < 0.5:   # 25-50%
            return 0.5 + (roi - 0.25) * 2  # 0.5-1.0 score
        else:  # 50%+
            return 1.0
    
    def _calculate_time_factor(self, opportunity_data: Dict[str, Any]) -> float:
        """Calculate time sensitivity factor"""
        vehicle_data = opportunity_data['vehicle']
        
        # Check if auction_end is available
        auction_end = vehicle_data.get('auction_end')
        if not auction_end:
            return 0.0
        
        try:
            if isinstance(auction_end, str):
                auction_end = datetime.fromisoformat(auction_end.replace('Z', '+00:00'))
            
            time_remaining = auction_end - datetime.now(auction_end.tzinfo)
            hours_remaining = time_remaining.total_seconds() / 3600
            
            # Bonus for auctions ending soon (but not too soon)
            if hours_remaining < 1:
                return 0.0  # Too late
            elif hours_remaining < 6:
                return 0.3  # High urgency bonus
            elif hours_remaining < 24:
                return 0.2  # Medium urgency bonus
            elif hours_remaining < 72:
                return 0.1  # Low urgency bonus
            else:
                return 0.0  # No urgency
                
        except Exception:
            return 0.0
    
    def _generate_recommendation(self, score: float, profit_margin: float, 
                                roi: float, risk_score: float) -> str:
        """Generate recommendation based on scores"""
        
        if score >= 0.8:
            return "STRONG BUY - Excellent opportunity with high profit potential"
        elif score >= 0.6:
            if risk_score < 0.3:
                return "BUY - Good opportunity with acceptable risk"
            else:
                return "CONSIDER - Good profits but higher risk"
        elif score >= 0.4:
            if profit_margin > 0.15:
                return "WATCH - Moderate opportunity, monitor for better price"
            else:
                return "PASS - Limited profit potential"
        elif score >= 0.2:
            return "PASS - Poor opportunity with low returns"
        else:
            return "AVOID - High risk or negative returns"
    
    def _estimate_days_to_sell(self, vehicle_data: Dict[str, Any], 
                              profit_margin: float) -> int:
        """Estimate days to sell based on vehicle characteristics"""
        
        # Base days to sell
        base_days = 45
        
        # Adjust based on vehicle type
        make = vehicle_data.get('make', '').lower()
        if make in ['toyota', 'honda', 'ford', 'chevrolet']:
            base_days -= 10  # Popular brands sell faster
        
        # Adjust based on age
        year = vehicle_data.get('year', datetime.now().year)
        age = datetime.now().year - year
        if age < 5:
            base_days -= 15  # Newer vehicles sell faster
        elif age > 15:
            base_days += 15  # Older vehicles take longer
        
        # Adjust based on mileage
        mileage = vehicle_data.get('mileage', 0)
        if mileage < 50000:
            base_days -= 10  # Low mileage sells faster
        elif mileage > 150000:
            base_days += 20  # High mileage takes longer
        
        # Adjust based on profit margin (pricing strategy)
        if profit_margin > 0.25:
            base_days += 10  # Higher margin = longer to sell
        elif profit_margin < 0.1:
            base_days -= 5   # Lower margin = faster sale
        
        # Adjust based on title status
        title_status = vehicle_data.get('title_status', 'clean').lower()
        if title_status in ['salvage', 'rebuilt', 'flood']:
            base_days += 30  # Problem titles take much longer
        
        return max(7, min(180, base_days))  # Constrain to 1 week - 6 months
    
    async def retrain(self):
        """Retrain opportunity scoring model"""
        # This model uses rule-based scoring, but could be enhanced
        # with ML to learn from successful vs unsuccessful opportunities
        print("Opportunity scorer uses rule-based scoring - no retraining needed")
    
    async def get_feature_importance(self) -> List[Dict[str, Any]]:
        """Get scoring factor importance"""
        factors = []
        for factor, weight in self.weights.items():
            factors.append({
                'feature': factor,
                'importance': abs(weight),
                'description': factor.replace('_', ' ').title()
            })
        
        factors.sort(key=lambda x: x['importance'], reverse=True)
        return factors
    
    async def batch_score(self, opportunities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score multiple opportunities in batch"""
        results = []
        
        for opportunity in opportunities:
            try:
                result = await self.score(opportunity)
                results.append(result)
            except Exception as e:
                # Add error result for failed scoring
                results.append({
                    'score': 0.0,
                    'error': str(e),
                    'recommendation': 'ERROR - Could not score opportunity'
                })
        
        return results