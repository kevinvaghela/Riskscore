import pandas as pd
import numpy as np
import re
from datetime import datetime


def trendline(index,data, order=1):
    coeffs = np.polyfit(index, list(data), order)
    slope = coeffs[-2]
    return float(slope)


def NumpySlope(df):
    
    df = df.copy(deep=True)

    # Regular expression pattern to match date format (YYYY-MM-DD)
    date_pattern = r'\d{4}-\d{2}-\d{2}'

    # Use a list comprehension to select columns with date names
    date_columns = [col for col in df.columns if re.match(date_pattern, col)]

    filtered_df = df[date_columns]

    slope_list = []

    for _ , data in filtered_df.iterrows():
        List = list(data)
        index = range(len(List))
        resultent=trendline(index,List)
        slope_list.append(resultent)

    df["numpy_slope"] = slope_list
    
    # sum of last x days
    row_sums = filtered_df.sum(axis=1)
    df["activity_total"] = row_sums

    df = df.drop(date_columns, axis=1)
    
    return df


def timeStamptoDate(df):
    
    df = df.copy(deep=True)

    df["first_invoice"] = pd.to_datetime(df['fFirstInvoiceDateTs'], unit='ms')
    df["fNextRenewalDate"] = pd.to_datetime(df["fNextRenewalDateTs"], unit='ms')
    df = df.drop(["fFirstInvoiceDateTs"], axis=1)
    
    return df


def get_renewal_date(df):

    df = df.copy(deep=True)
    # getting renewal date using first invoice date if it is less then today then we are assuing they renew and add (first invoice yeat+1) otherwise(first invoice yeat)
    df["first_invoice"] = pd.to_datetime(df["first_invoice"])

    df['year'] = (pd.DatetimeIndex(df['first_invoice']).year).astype("Int32")
    df['month'] = (pd.DatetimeIndex(df['first_invoice']).month).astype("Int32")
    df['day'] = (pd.DatetimeIndex(df['first_invoice']).day).astype("Int32")

    df = df[["uuid","fName","first_invoice","fNextRenewalDateTs","fNextRenewalDate","year","month","day","ActiveUniqueUsers","numpy_slope","activity_total"]]

    df["days_use"] = df["first_invoice"].apply(lambda x: -(x - datetime.now()).days)

    df["days_use"] = df["days_use"].astype("Int32")

    year_lst = []
    currentDay = datetime.now().day
    currentMonth = datetime.now().month
    currentYear = datetime.now().year

    for first_invoice, year, month, day in zip(df["first_invoice"], df["year"], df["month"], df["day"]):
        if len(str(first_invoice)) <= 5:
            year_lst.append(np.NaN)
        else: 
            if month < currentMonth:
                year_lst.append(currentYear+1)
            elif month > currentMonth:
                year_lst.append(currentYear)
            elif month == currentMonth and day > currentDay:
                year_lst.append(currentYear)
            elif month == currentMonth and day <= currentDay:
                year_lst.append(currentYear+1)

    df["renewal_year"] = year_lst
    df["renewal_year"] = df["renewal_year"].astype("Int32")
    df["renewal_date"] = df["renewal_year"].astype(str) + "-" + df["month"].astype(str) + "-" + df["day"].astype(str)
    # df["renewal_date"] = df["renewal_date"].replace({"<NA>-<NA>-<NA>":np.NaN})
    df["renewal_date"] = pd.to_datetime(df["renewal_date"])

    # df["fNextRenewalDate"] = df['fNextRenewalDate'].fillna(df['renewal_date'])

    # Get today's date
    today = datetime.today().date()

    # Define a function to apply the logic
    def choose_date(row):
        if pd.notnull(row['fNextRenewalDate']) and row['fNextRenewalDate'].date() > today:
            return row['fNextRenewalDate']
        else:
            return row['renewal_date']
        
    # Apply the function to create the output column
    df['Renew_date'] = df.apply(choose_date, axis=1)

    df["days_remaining"] = df["Renew_date"].apply(lambda x: (x - datetime.now()).days)

    return df


def riskUsage(df, weight):
    
    df = df.copy(deep=True)
    
    # Divide activity_total by ActiveUniqueUsers, handle division by zero
    df["Manual_per_user"] = np.where(df['ActiveUniqueUsers'] == 0, 0, df['activity_total'] / df['ActiveUniqueUsers'])
    
    max_usage_per_user = df["Manual_per_user"].max()
    
    # Divide the "result" column by the maximum value, handle division by zero
    df['Usage_Factor'] = np.where(max_usage_per_user == 0, 0, df['Manual_per_user'] / max_usage_per_user)
    
    # Apply the transformation (1 - value) * weight to the "result" column
    df["RISK_USAGE"] = (1 - df['Usage_Factor']) * weight
    
    return df


def riskRenewalDate(df, weight):
    
    df = df.copy()
    
    # Calculate the new column, handling 0 values
    df['Days_to_Renew_factor'] = 1 - (df['days_remaining'] / 365)
    df['Days_to_Renew_factor'] = df['Days_to_Renew_factor'].apply(lambda x: 0 if x < 0 else x) 
    df['RISK_RENEWAL_DATE'] = df['RISK_USAGE'] * (df['Days_to_Renew_factor'] * weight)
    
    return df


def riskNumpyFactor(df, weight):
    
    df = df.copy(deep=True)
    
    # Calculate the new column
    df['NumPy_Factor'] = -0.1 * df['numpy_slope'] + 1   
    df['RISK_SCORE'] = df['RISK_RENEWAL_DATE'] * (df['NumPy_Factor'] * weight)
    
    return df


def riskScoreUI(df):
    
    df = df.copy(deep=True)

    max_risk_score = df["RISK_SCORE"].max()
    df["UI_RISK"] = (df["RISK_SCORE"]/max_risk_score) * 10
    
    return df


def get_result_json(df):

    df = df.copy(deep=True)

    df = df[["uuid","UI_RISK"]]
    df['risk_score_integer'] = df['UI_RISK'].apply(lambda x: int(round(x, 5) * 1000) if pd.notna(x) and x != 0 else 0)
    current_date = datetime.now().strftime("%Y%m%d")
    
    current_timestamp = int(datetime.now().timestamp() * 1000)
    
    result_lst = []
    for uuid, risk_score, risk_score_integer in df[["uuid","UI_RISK","risk_score_integer"]].values:
        result_dict = {}
        result_dict["uuid"] = uuid
        # try:
        #     result_dict["risk_score"] = str(risk_score)
        # except:
        #     result_dict["risk_score"] = ""
            
        try:
            result_dict["fRiskScore"] = str(risk_score_integer)
        except:
            result_dict["fRiskScore"] = ""
        
        if isinstance(risk_score, float):
            result_dict["fRiskScoreTs"] = str(current_timestamp)
        else:
            result_dict["fRiskScoreTs"] = ""
            
        result_lst.append(result_dict)
        
    # with open(f"../output/risk_score_{current_date}.json", "w") as json_file:
        # json.dump(result_lst, json_file, indent=4)

    return result_lst


def getMeRiskScore(requestData):
    
    df = pd.DataFrame(requestData)

    df = NumpySlope(df)
    df = timeStamptoDate(df)
    df = get_renewal_date(df)
    df = riskUsage(df, weight=1)
    df = riskRenewalDate(df, weight=1)
    df = riskNumpyFactor(df, weight=1)
    df = riskScoreUI(df)

    df.to_csv("../Output/ver2_data_20230922.csv", index=False)

    output_json = get_result_json(df)

    return output_json

requestData_json = [{"uuid": "vienna_woods_hotel", "fName": "Vienna Woods Hotel", "fCustomerType": "paying_customer", "fFirstInvoiceDateTs": 1617235200000, "fNextRenewalDateTs": 0, "ActiveUniqueUsers": 0, "2023-06-22": 0, "2023-06-23": 0, "2023-06-24": 0, "2023-06-25": 0, "2023-06-26": 0, "2023-06-27": 0, "2023-06-28": 0, "2023-06-29": 0, "2023-06-30": 0, "2023-07-01": 0, "2023-07-02": 0, "2023-07-03": 0, "2023-07-04": 0, "2023-07-05": 0, "2023-07-06": 0, "2023-07-07": 0, "2023-07-08": 0, "2023-07-09": 0, "2023-07-10": 0, "2023-07-11": 0, "2023-07-12": 0, "2023-07-13": 0, "2023-07-14": 0, "2023-07-15": 0, "2023-07-16": 0, "2023-07-17": 0, "2023-07-18": 0, "2023-07-19": 0, "2023-07-20": 0, "2023-07-21": 0, "2023-07-22": 0, "2023-07-23": 0, "2023-07-24": 0, "2023-07-25": 0, "2023-07-26": 0, "2023-07-27": 0, "2023-07-28": 0, "2023-07-29": 0, "2023-07-30": 0, "2023-07-31": 0, "2023-08-01": 0, "2023-08-02": 0, "2023-08-03": 0, "2023-08-04": 0, "2023-08-05": 0, "2023-08-06": 0, "2023-08-07": 0, "2023-08-08": 0, "2023-08-09": 0, "2023-08-10": 0, "2023-08-11": 0, "2023-08-12": 0, "2023-08-13": 0, "2023-08-14": 0, "2023-08-15": 0, "2023-08-16": 0, "2023-08-17": 0, "2023-08-18": 0, "2023-08-19": 0, "2023-08-20": 0, "2023-08-21": 0, "2023-08-22": 0, "2023-08-23": 0, "2023-08-24": 0, "2023-08-25": 0, "2023-08-26": 0, "2023-08-27": 0, "2023-08-28": 0, "2023-08-29": 0, "2023-08-30": 0, "2023-08-31": 0, "2023-09-01": 0, "2023-09-02": 0, "2023-09-03": 0, "2023-09-04": 0, "2023-09-05": 0, "2023-09-06": 0, "2023-09-07": 0, "2023-09-08": 0, "2023-09-09": 0, "2023-09-10": 0, "2023-09-11": 0, "2023-09-12": 0, "2023-09-13": 0, "2023-09-14": 0, "2023-09-15": 0, "2023-09-16": 0, "2023-09-17": 0, "2023-09-18": 0, "2023-09-19": 0},
                    {"uuid": "vienna_woods_hotel", "fName": "Vienna Woods Hotel", "fCustomerType": "paying_customer", "fFirstInvoiceDateTs": 1617235200000, "fNextRenewalDateTs": 1696071876000, "ActiveUniqueUsers": 0, "2023-06-22": 0, "2023-06-23": 0, "2023-06-24": 0, "2023-06-25": 0, "2023-06-26": 0, "2023-06-27": 0, "2023-06-28": 0, "2023-06-29": 0, "2023-06-30": 0, "2023-07-01": 0, "2023-07-02": 0, "2023-07-03": 0, "2023-07-04": 0, "2023-07-05": 0, "2023-07-06": 0, "2023-07-07": 0, "2023-07-08": 0, "2023-07-09": 0, "2023-07-10": 0, "2023-07-11": 0, "2023-07-12": 0, "2023-07-13": 0, "2023-07-14": 0, "2023-07-15": 0, "2023-07-16": 0, "2023-07-17": 0, "2023-07-18": 0, "2023-07-19": 0, "2023-07-20": 0, "2023-07-21": 0, "2023-07-22": 0, "2023-07-23": 0, "2023-07-24": 0, "2023-07-25": 0, "2023-07-26": 0, "2023-07-27": 0, "2023-07-28": 0, "2023-07-29": 0, "2023-07-30": 0, "2023-07-31": 0, "2023-08-01": 0, "2023-08-02": 0, "2023-08-03": 0, "2023-08-04": 0, "2023-08-05": 0, "2023-08-06": 0, "2023-08-07": 0, "2023-08-08": 0, "2023-08-09": 0, "2023-08-10": 0, "2023-08-11": 0, "2023-08-12": 0, "2023-08-13": 0, "2023-08-14": 0, "2023-08-15": 0, "2023-08-16": 0, "2023-08-17": 0, "2023-08-18": 0, "2023-08-19": 0, "2023-08-20": 0, "2023-08-21": 0, "2023-08-22": 0, "2023-08-23": 0, "2023-08-24": 0, "2023-08-25": 0, "2023-08-26": 0, "2023-08-27": 0, "2023-08-28": 0, "2023-08-29": 0, "2023-08-30": 0, "2023-08-31": 0, "2023-09-01": 0, "2023-09-02": 0, "2023-09-03": 0, "2023-09-04": 0, "2023-09-05": 0, "2023-09-06": 0, "2023-09-07": 0, "2023-09-08": 0, "2023-09-09": 0, "2023-09-10": 0, "2023-09-11": 0, "2023-09-12": 0, "2023-09-13": 0, "2023-09-14": 0, "2023-09-15": 0, "2023-09-16": 0, "2023-09-17": 0, "2023-09-18": 0, "2023-09-19": 0}]

requestData = pd.DataFrame(requestData_json)
getMeRiskScore(requestData)

# requestData = pd.read_json(r"../Data/version2_requestdata.json")
    # getMeRiskScore(requestData)

# check = getMeRiskScore(requestData)
# print(check)