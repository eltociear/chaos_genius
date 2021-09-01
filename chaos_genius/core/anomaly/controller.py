import datetime

import pandas as pd

from chaos_genius.core.anomaly.processor import ProcessAnomalyDetection
from chaos_genius.core.anomaly.utils import (
    get_anomaly_df, 
    get_dq_missing_data, 
    get_last_date_in_db
)

from chaos_genius.databases.models.data_source_model import DataSource
from chaos_genius.databases.models.anomaly_data_model import AnomalyDataOutput, db

class AnomalyDetectionController(object):
    def __init__(self, kpi_info, save_model=False, debug=False):
        self.kpi_info = kpi_info

        # TODO: Add these in kpi_info
        self.kpi_info["freq"] = self.kpi_info.get("freq", "D")
        self.kpi_info["period"] = self.kpi_info.get("period", 90)
        self.kpi_info["model_name"] = self.kpi_info.get("model_name", "StdDeviModel")

        self.save_model = save_model
        self.debug = debug

    def _load_anomaly_data(self) -> pd.DataFrame:
        """Loads KPI data from its datastore, preprocesses it and 
        returns it for anomaly detection 

        :return: Dataframe with all of KPI's data for the last 
        N days/hours
        :rtype: pd.DataFrame
        """

        conn = DataSource.get_by_id(self.kpi_info["data_source"])

        last_date = self._get_last_date_in_db("overall")

        print(last_date)

        df = get_anomaly_df(self.kpi_info, conn.as_dict, last_date)

        dt_col = self.kpi_info['datetime_column']

        df[dt_col] = pd.to_datetime(df[dt_col])

        return df

    def _get_last_date_in_db(
        self,
        series: str,
        subgroup: str = None
    ) -> datetime.datetime:
        """Returns the last date for which we have data for the given 
        series

        :param series: Type of series
        :type series: str
        :param subgroup: Subtype of series
        :type subgroup: str
        :return: Last date for which we have data for the given series
        :rtype: datetime.datetime
        """
        
        return get_last_date_in_db(self.kpi_info["id"], series, subgroup)

    def _detect_anomaly(
        self,
        model_name: str,
        input_data: pd.DataFrame,
        last_date: datetime.datetime,
        series,
        subgroup
    ) -> pd.DataFrame:
        """Detects anomaly in the given data

        :param model_name: name of the model used for anomaly detection
        :type model_name: str
        :param input_data: Dataframe with metric's data
        :type input_data: pd.DataFrame
        :param last_date: Last date for which we have output data
        :type last_date: datetime.datetime
        :return: Dataframe with anomaly data
        :rtype: pd.DataFrame
        """

        input_data = input_data.reset_index().rename(columns={
            self.kpi_info['datetime_column']: 'dt',
            self.kpi_info['metric']: 'y'
        })

        return ProcessAnomalyDetection(
            model_name,
            input_data,
            last_date,
            self.kpi_info["period"],
            self.kpi_info["table_name"],
            series,
            subgroup,
            self.kpi_info.get("model_kwargs", {})
        ).predict()

    def _save_anomaly_output(
        self,
        anomaly_output: pd.DataFrame,
        series: str,
        subgroup: str = None
    ) -> None:
        """Saves anomaly output to the output DB

        :param anomaly_output: Dataframe with anomaly data
        :type anomaly_output: pd.DataFrame
        :param series: Type of series
        :type series: str
        :param subgroup: Subgroup of the KPI
        :type subgroup: str
        """
        name = self.kpi_info['name']
        table = self.kpi_info['table_name']
        model_name = self.kpi_info['model_name']

        if self.debug:
            print("SAVING")
            print(name, table, model_name)
            print(series, subgroup)
            print(anomaly_output)

        anomaly_output = anomaly_output.rename(columns={"dt": "data_datetime", "anomaly": "is_anomaly"})
        anomaly_output["kpi_id"] = self.kpi_info["id"]
        anomaly_output["anomaly_type"] = series
        anomaly_output["series_type"] = subgroup
        
        anomaly_output.to_sql(AnomalyDataOutput.__tablename__, db.engine, if_exists="append")

    def _get_subgroup_list(
        self,
        input_data: pd.DataFrame
    ) -> list:
        """Returns list of subgroups for which we want to run anomaly 
        detection

        :return: List of subgroups
        :rtype: list
        """

        subgroups = []
        for dim in self.kpi_info["dimensions"]:
            subgroup = []
            for category in input_data[dim].unique():
                subgroup.append(f"`{dim}`==\"{category}\"")
            subgroups.append(subgroup)

        dp = {}

        def gen_groups(level=0, k=0):
            if len(subgroups[level:]) == 1:
                return subgroups[level]

            if (level, k) in dp:
                return dp[(level, k)]

            ans = []
            for i in subgroups[level]:
                ans.extend(
                    ' and '.join([i, x]) for x in gen_groups(level+1, k+1))
            dp[(level, k)] = ans
            return ans

        return gen_groups()

    def _filter_subgroups(
        self, subgroups: list, input_data: pd.DataFrame
    ) -> list:
        """Filters out irrelevant subgroups

        :param subgroups: List of subgroups
        :type subgroups: list
        :return: List of subgroups
        :rtype: list
        """

        grouped_input_data = input_data\
            .groupby(self.kpi_info['dimensions'])\
            .agg({self.kpi_info['metric']:"count"})
        
        filtered_subgroups = []

        for subgroup in subgroups:
            try:
                if grouped_input_data.query(subgroup)[self.kpi_info["metric"]]\
                    .iloc[0] >= self.kpi_info["period"]:
                    filtered_subgroups.append(subgroup)
            except IndexError:
                pass
        return filtered_subgroups

    def _run_anomaly_for_series(
        self,
        input_data: pd.DataFrame,
        series: str,
        subgroup: str = None
    ) -> None:
        """Runs anomaly detection for the given series

        :param series: Type of series
        :type series: str
        :param subgroup: Subgroup of the KPI
        :type subgroup: str
        """

        dt_col = self.kpi_info['datetime_column']
        metric_col = self.kpi_info['metric']
        freq = self.kpi_info.get('freq', 'D')
        agg = self.kpi_info["aggregation"]

        series_data = None

        if series == 'dq':
            if subgroup == 'missing':
                series_data = get_dq_missing_data(
                    input_data, dt_col, metric_col
                )

            else:
                series_data = input_data.set_index(dt_col) \
                    .resample(freq).agg({metric_col: subgroup})

        else:
            series_data = input_data.set_index(dt_col) \
                .resample(freq).agg({metric_col: agg})

        model_name = self.kpi_info["model_name"]

        last_date = self._get_last_date_in_db(series, subgroup)


        overall_anomaly_output = self._detect_anomaly(
            model_name, series_data, last_date, series, subgroup)

        self._save_anomaly_output(overall_anomaly_output, series, subgroup) 


    def detect(self) -> None:
        # TODO: Docstring
        if self.debug:
            print(self.kpi_info["model_name"])

        input_data = self._load_anomaly_data()

        if self.debug:
            print('overall')

        self._run_anomaly_for_series(input_data, "overall")

        subgroups = self._get_subgroup_list(input_data)

        # FIXME: Fix filtering logic
        filtered_subgroups = self._filter_subgroups(subgroups, input_data)

        if self.debug:
            filtered_subgroups = filtered_subgroups[:5]

        for subgroup in filtered_subgroups:
            if self.debug:
                print(subgroup)

            self._run_anomaly_for_series(input_data, "subdim", subgroup)

        for dq_subgroup in ["max", "count", "mean", "missing"]:
            if self.debug:
                print(dq_subgroup)

            try:
                self._run_anomaly_for_series(input_data, "dq", dq_subgroup)
            except Exception as e:
                print(e)
