import traceback

def evaluate_full_tractor_analysis(input_data, age_years):
    print('in evaluate_full_tractor_analysis--------------\n',input_data,age_years)
    try:
        rust_percent = int(input_data["rust_tire_analysis"]["rust_percent"])
        tires = input_data["rust_tire_analysis"]["tires"]
        max_price = input_data["top_price_fuzzy_match"]["max_price"]

        # Weights
        rust_weight = 0.4
        tire_weight = 0.6

        # Rust depreciation
        rust_depreciation = rust_percent * rust_weight

        # Tire depreciation + classification
        tire_values = []
        tire_conditions = {}

        for position, data in tires.items():
            percent = data["percent"]
            print(percent)
            if(isinstance(percent,int)):
                tire_values.append(percent)
            
            if percent =='not_visible' and isinstance(percent,str):
                tire_conditions[position] = "not_visible"
            elif percent >= 70:
                tire_conditions[position] = "Good"
            elif percent >= 40:
                tire_conditions[position] = "Average"
            else:
                tire_conditions[position] = "Bad"
        print(tire_values)
        avg_tire_remaining = sum(tire_values) / len(tire_values)
        avg_tire_wear = 100 - avg_tire_remaining
        tire_depreciation = avg_tire_wear * tire_weight
        try:
            age_years=int(age_years)
        except:
            age_years=1
        # Age depreciation
        if age_years <= 1:
            age_depreciation = 7
        elif age_years <= 3:
            age_depreciation = 11
        elif age_years <= 5:
            age_depreciation = 17
        elif age_years <= 7:
            age_depreciation = 23
        elif age_years <= 10:
            age_depreciation = 31
        else:
            age_depreciation = 70

        # Total depreciation
        total_depreciation = rust_depreciation + tire_depreciation + age_depreciation
        total_depreciation = min(total_depreciation, 95)  
        resale_percent = 100 - total_depreciation

        # Resale value 
        resale_value = round(max_price * (resale_percent / 100))
        print(resale_percent)

        input_data["valuation_result"] = {
        "brand": input_data["brand_model_prediction"]["brand"],
        "model": input_data["brand_model_prediction"]["model"],
        "total_depreciation_percent": round(total_depreciation, 2),
        "estimated_resale_value_percent": round(resale_percent, 2),
        "estimated_resale_price_inr": resale_value,
        "rust_depreciation": round(rust_depreciation, 2),
        "tire_depreciation": round(tire_depreciation, 2),
        "age_depreciation": age_depreciation,
        "tire_conditions": tire_conditions
    }

        return input_data
    
    except Exception as e:
        print(traceback.format_exc())
        print(e)
        return input_data
