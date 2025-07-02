"""
Harness - AWS Cost Explorer Service
Real implementation using AWS Cost Explorer API
"""
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import boto3
from botocore.exceptions import ClientError

from backend.models.admin import CostData, ServiceCost, DailyCost, MonthlyTrend, CostAnomaly


class CostExplorerService:
    """Service for retrieving AWS cost data"""
    
    def __init__(self, region: str = 'us-east-1'):
        self.client = boto3.client('ce', region_name=region)
        self.budgets_client = boto3.client('budgets', region_name=region)
        self.account_id = boto3.client('sts').get_caller_identity()['Account']
    
    async def get_costs(self, time_range: str) -> CostData:
        """Get AWS cost data for the specified time range"""
        days = {"7d": 7, "30d": 30, "90d": 90}[time_range]
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)
        
        # Get daily costs
        daily_costs = await self._get_daily_costs(start_date, end_date)
        
        # Get current month costs
        current_month_start = datetime.utcnow().replace(day=1).date()
        current_month_costs = await self._get_period_costs(current_month_start, end_date)
        
        # Get last month costs for comparison
        last_month_end = current_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        last_month_costs = await self._get_period_costs(last_month_start, last_month_end)
        
        # Calculate change percentage
        change = 0
        if last_month_costs > 0:
            days_in_current = (end_date - current_month_start).days + 1
            days_in_month = 30  # Approximate
            projected_current = (current_month_costs / days_in_current) * days_in_month
            change = ((projected_current - last_month_costs) / last_month_costs) * 100
        
        # Get service breakdown
        service_breakdown = await self._get_service_breakdown(current_month_start, end_date)
        
        # Get monthly trends
        monthly_trends = await self._get_monthly_trends()
        
        # Get anomalies
        anomalies = await self._get_anomalies()
        
        # Get today's cost
        today_cost = daily_costs[0].total if daily_costs else 0
        
        # Calculate projection
        avg_daily = sum(dc.total for dc in daily_costs[:7]) / min(7, len(daily_costs)) if daily_costs else 0
        days_in_month = 30
        projected_total = avg_daily * days_in_month
        
        # Get budget information
        budget_info = await self._get_budget_info()
        monthly_budget = budget_info.get('limit', 5000)
        budget_utilization = (current_month_costs / monthly_budget) * 100 if monthly_budget > 0 else 0
        
        return CostData(
            current_month={
                "total": round(current_month_costs, 2),
                "change": round(change, 1)
            },
            today={
                "total": round(today_cost, 2)
            },
            projected={
                "total": round(projected_total, 2)
            },
            budget_utilization=round(budget_utilization, 1),
            monthly_budget=monthly_budget,
            daily_costs=daily_costs,
            service_breakdown=service_breakdown,
            monthly_trends=monthly_trends,
            anomalies=anomalies if anomalies else None
        )
    
    async def _get_daily_costs(self, start_date, end_date) -> List[DailyCost]:
        """Get daily cost breakdown"""
        try:
            response = self.client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                Filter={
                    'Tags': {
                        'Key': 'Project',
                        'Values': ['Harness']
                    }
                }
            )
            
            daily_costs = []
            for result in response['ResultsByTime']:
                date = result['TimePeriod']['Start']
                amount = float(result['Total']['UnblendedCost']['Amount'])
                daily_costs.append(DailyCost(date=date, total=round(amount, 2)))
            
            return daily_costs
            
        except ClientError:
            # Return empty list if API call fails
            return []
    
    async def _get_period_costs(self, start_date, end_date) -> float:
        """Get total costs for a period"""
        try:
            response = self.client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                Filter={
                    'Tags': {
                        'Key': 'Project',
                        'Values': ['Harness']
                    }
                }
            )
            
            if response['ResultsByTime']:
                return float(response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
            return 0.0
            
        except ClientError:
            return 0.0
    
    async def _get_service_breakdown(self, start_date, end_date) -> List[ServiceCost]:
        """Get cost breakdown by service"""
        try:
            response = self.client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
                Filter={
                    'Tags': {
                        'Key': 'Project',
                        'Values': ['Harness']
                    }
                }
            )
            
            services = []
            service_map = {
                'Amazon Elastic Compute Cloud - Compute': ('EC2', 'Compute instances for ECS and training'),
                'Amazon Simple Storage Service': ('S3', 'Storage for papers and models'),
                'Amazon Relational Database Service': ('RDS', 'PostgreSQL databases'),
                'Amazon SageMaker': ('SageMaker', 'ML training and endpoints'),
                'Amazon CloudFront': ('CloudFront', 'CDN for web assets'),
                'Amazon ElastiCache': ('ElastiCache', 'Redis caching layer'),
                'AWS Lambda': ('Lambda', 'Serverless compute'),
                'Amazon Route 53': ('Route53', 'DNS management')
            }
            
            if response['ResultsByTime']:
                for group in response['ResultsByTime'][0]['Groups']:
                    service_name = group['Keys'][0]
                    amount = float(group['Metrics']['UnblendedCost']['Amount'])
                    
                    if service_name in service_map:
                        name, description = service_map[service_name]
                    else:
                        name = service_name.split(' - ')[0].replace('Amazon ', '').replace('AWS ', '')
                        description = service_name
                    
                    if amount > 0:
                        services.append(ServiceCost(
                            name=name,
                            description=description,
                            cost=round(amount, 2),
                            change=0  # Would need historical data for accurate change
                        ))
            
            # Sort by cost descending
            services.sort(key=lambda x: x.cost, reverse=True)
            
            # Group small services into "Other"
            if len(services) > 6:
                other_cost = sum(s.cost for s in services[5:])
                services = services[:5]
                services.append(ServiceCost(
                    name="Other",
                    description="Other AWS services",
                    cost=round(other_cost, 2),
                    change=0
                ))
            
            return services
            
        except ClientError:
            return []
    
    async def _get_monthly_trends(self) -> List[MonthlyTrend]:
        """Get monthly cost trends by category"""
        trends = []
        end_date = datetime.utcnow().date()
        
        for i in range(6):
            month_end = (end_date.replace(day=1) - timedelta(days=1))
            month_start = month_end.replace(day=1)
            
            # Move to previous month
            end_date = month_start - timedelta(days=1)
            
            try:
                response = self.client.get_cost_and_usage(
                    TimePeriod={
                        'Start': month_start.strftime('%Y-%m-%d'),
                        'End': month_end.strftime('%Y-%m-%d')
                    },
                    Granularity='MONTHLY',
                    Metrics=['UnblendedCost'],
                    GroupBy=[{'Type': 'COST_CATEGORY', 'Key': 'harness-cost-categories'}],
                    Filter={
                        'Tags': {
                            'Key': 'Project',
                            'Values': ['Harness']
                        }
                    }
                )
                
                categories = {
                    'Compute': 0,
                    'Storage': 0,
                    'Database': 0,
                    'ML': 0,
                    'Other': 0
                }
                
                if response['ResultsByTime']:
                    for group in response['ResultsByTime'][0]['Groups']:
                        category = group['Keys'][0]
                        amount = float(group['Metrics']['UnblendedCost']['Amount'])
                        if category in categories:
                            categories[category] = round(amount, 2)
                
                trends.append(MonthlyTrend(
                    month=month_start.strftime('%B %Y'),
                    compute=categories['Compute'],
                    storage=categories['Storage'],
                    database=categories['Database'],
                    ml=categories['ML'],
                    other=categories['Other']
                ))
                
            except ClientError:
                # Add empty trend if API fails
                trends.append(MonthlyTrend(
                    month=month_start.strftime('%B %Y'),
                    compute=0,
                    storage=0,
                    database=0,
                    ml=0,
                    other=0
                ))
        
        return trends[::-1]  # Reverse to show oldest first
    
    async def _get_anomalies(self) -> List[CostAnomaly]:
        """Get cost anomalies"""
        try:
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=30)
            
            response = self.client.get_anomalies(
                DateInterval={
                    'StartDate': start_date.strftime('%Y-%m-%d'),
                    'EndDate': end_date.strftime('%Y-%m-%d')
                },
                MaxResults=10
            )
            
            anomalies = []
            for anomaly in response.get('Anomalies', []):
                if anomaly['AnomalyScore']['CurrentScore'] > 0.7:  # High confidence anomalies
                    service = anomaly.get('RootCauses', [{}])[0].get('Service', 'Unknown')
                    anomalies.append(CostAnomaly(
                        service=service,
                        description=f"Unusual cost spike detected - {anomaly.get('Feedback', 'Under investigation')}",
                        amount=float(anomaly['Impact']['TotalImpact']),
                        date=anomaly['AnomalyStartDate']
                    ))
            
            return anomalies
            
        except ClientError:
            return []
    
    async def _get_budget_info(self) -> Dict[str, float]:
        """Get budget information"""
        try:
            response = self.budgets_client.describe_budget(
                AccountId=self.account_id,
                BudgetName='harness-monthly-budget'
            )
            
            budget = response['Budget']
            return {
                'limit': float(budget['BudgetLimit']['Amount']),
                'actual': float(budget['CalculatedSpend']['ActualSpend']['Amount']),
                'forecasted': float(budget['CalculatedSpend']['ForecastedSpend']['Amount'])
            }
            
        except ClientError:
            return {'limit': 5000, 'actual': 0, 'forecasted': 0}