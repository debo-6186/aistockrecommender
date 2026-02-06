def df_to_dict_str_keys(df):
    if df is None:
        return None
    # Convert DataFrame to dict, then ensure all keys are strings
    d = df.to_dict()
    if isinstance(d, dict):
        return {str(k): {str(kk): vv for kk, vv in v.items()} for k, v in d.items()}
    return d