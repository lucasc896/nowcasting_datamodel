""" Read database functions

1. Get the latest forecast
2. get the latest forecasts for all gsp ids
3. get all forecast values
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import desc, text
from sqlalchemy.orm import contains_eager, joinedload
from sqlalchemy.orm.session import Session

from nowcasting_datamodel import N_GSP
from nowcasting_datamodel.models import (
    InputDataLastUpdatedSQL,
    LocationSQL,
    MLModelSQL,
    PVSystemSQL,
    StatusSQL,
    national_gb_label,
)
from nowcasting_datamodel.models.forecast import (
    ForecastSQL,
    ForecastValueLatestSQL,
    ForecastValueSevenDaysSQL,
    ForecastValueSQL,
)

logger = logging.getLogger(__name__)


def get_latest_input_data_last_updated(
    session: Session,
) -> InputDataLastUpdatedSQL:
    """
    Read last input data last updated

    :param session: database session

    return: Latest input data object
    """

    # start main query
    query = session.query(InputDataLastUpdatedSQL)

    # this make the newest ones comes to the top
    query = query.order_by(InputDataLastUpdatedSQL.created_utc.desc())

    # get all results
    input_data = query.first()

    logger.debug("Found latest input data")

    return input_data


def get_latest_status(
    session: Session,
) -> StatusSQL:
    """
    Read last input data last updated

    :param session: database session

    return: Latest input data object
    """

    # start main query
    query = session.query(StatusSQL)

    # this make the newest ones comes to the top
    query = query.order_by(StatusSQL.created_utc.desc())

    # get all results
    input_data = query.first()

    logger.debug("Found latest status")

    return input_data


def update_latest_input_data_last_updated(
    session: Session, component: str, update_datetime: Optional[datetime] = None
):
    """
    Update the table InputDataLastUpdatedSQL with a new valye

    :param session:
    :param component: This should be gsp, pv, nwp or satellite
    :param update_datetime: the datetime is should be updated.
        Default is None, so will be set to now
    :return:
    """

    # For the moment we load the latest, update it and save a new one.
    # This may be a problem if these function is run at the same twice,
    # but for the moment lets ignore this

    if update_datetime is None:
        update_datetime = datetime.now(tz=timezone.utc)

    # get latest
    latest_input_data_last_updated = get_latest_input_data_last_updated(session=session)

    if latest_input_data_last_updated is None:
        logger.warning("Could not find any 'InputDataLastUpdatedSQL' so will create one.")
        now = datetime(1960, 1, 1, tzinfo=timezone.utc)
        latest_input_data_last_updated = InputDataLastUpdatedSQL(
            gsp=now, nwp=now, pv=now, satellite=now
        )

    # set new value
    setattr(latest_input_data_last_updated, component, update_datetime)

    # save to database
    session.add(latest_input_data_last_updated)
    session.commit()


def get_latest_forecast(
    session: Session,
    gsp_id: Optional[int] = None,
    historic: bool = False,
    start_target_time: Optional[datetime] = None,
) -> ForecastSQL:
    """
    Read forecasts

    :param session: database session
    :param gsp_id: optional to gsp id, to filter query on
        If None is given then all are returned.
    :param session: database session
    :param historic: Option to load historic values or not
    :param start_target_time:
        Filter: forecast values target time should be larger than this datetime

    return: List of forecasts objects from database
    """

    logger.debug(f"Getting latest forecast for gsp {gsp_id}")

    if gsp_id is not None:
        gsp_ids = [gsp_id]
    else:
        gsp_ids = None

    forecasts = get_latest_forecast_for_gsps(
        session=session,
        start_target_time=start_target_time,
        historic=historic,
        gsp_ids=gsp_ids,
    )

    if forecasts is None:
        return None
    if len(forecasts) == 0:
        return None

    forecast = forecasts[0]

    # sort list
    logger.debug(
        f"sorting 'forecast_values_latest' values. "
        f"There are {len(forecast.forecast_values_latest)}"
    )
    if forecast.forecast_values_latest is not None:
        forecast.forecast_values_latest = sorted(
            forecast.forecast_values_latest, key=lambda d: d.target_time
        )

    logger.debug(f"Found forecasts for gsp id: {gsp_id} {historic=} {forecast=}")

    return forecast


def sort_forecast_values(forecast: ForecastSQL):
    """Sort forecast values"""
    if forecast.historic:
        variable = "forecast_values_latest"
    else:
        variable = "forecast_values"

    if getattr(forecast, variable) is not None:
        setattr(
            forecast, variable, sorted(getattr(forecast, variable), key=lambda d: d.target_time)
        )

    return forecast


def sort_all_forecast_value(forecasts: List[ForecastSQL]):
    """
    Sorting all forecasts

    This may be possible in the sql query, but so far have found it hard to do it.
    Can't just add it to ORDER BY items, due to sub query.

    :param forecasts:  list of forecasts
    :return: list of forecasts, but with sorted forecat values
    """
    """ Sorting all forecasts"""

    logger.debug("sorting 'forecast_values_latest' or 'forecast_values' values.")

    for forecast in forecasts:
        sort_forecast_values(forecast=forecast)

    logger.debug("sorting done")

    return forecasts


def get_all_gsp_ids_latest_forecast(
    session: Session,
    start_created_utc: Optional[datetime] = None,
    start_target_time: Optional[datetime] = None,
    preload_children: Optional[bool] = False,
    historic: bool = False,
) -> List[ForecastSQL]:
    """
    Read forecasts

    :param session: database session
    :param start_created_utc: Filter: forecast creation time should be larger than this datetime
    :param start_target_time:
        Filter: forecast values target time should be larger than this datetime
    :param preload_children: Option to preload children. This is a speed up, if we need them.
    :param historic: Option to load historic values or not

    return: List of forecasts objects from database
    """

    logger.debug("Getting latest forecast for all gsps")

    return get_latest_forecast_for_gsps(
        session=session,
        start_created_utc=start_created_utc,
        start_target_time=start_target_time,
        preload_children=preload_children,
        historic=historic,
        gsp_ids=list(range(0, N_GSP + 1)),
    )


def get_latest_forecast_for_gsps(
    session: Session,
    start_created_utc: Optional[datetime] = None,
    start_target_time: Optional[datetime] = None,
    end_target_time: Optional[datetime] = None,
    preload_children: Optional[bool] = False,
    historic: bool = False,
    gsp_ids: List[int] = None,
):
    """
    Read forecasts

    :param session: database session
    :param start_created_utc: Filter: forecast creation time should be larger than this datetime
    :param start_target_time:
        Filter: forecast values target time should be larger than this datetime
    :param end_target_time:
        Filter: forecast values target time should be before than this datetime
    :param preload_children: Option to preload children. This is a speed up, if we need them.
    :param historic: Option to load historic values or not
    :param gsp_ids: Option to filter on gsps. If None, then only the lastest forecast is loaded.

    :return: List of forecasts objects from database

    """
    order_by_cols = []

    # start main query
    query = session.query(ForecastSQL)

    # filter on created_utc
    if start_created_utc is not None:
        query = query.filter(ForecastSQL.created_utc >= start_created_utc)

    # join with location table and filter
    if gsp_ids is not None:
        if not historic:
            # for historic they are already distinct
            query = query.distinct(LocationSQL.gsp_id)
        query = query.filter(LocationSQL.gsp_id.in_(gsp_ids))
        order_by_cols.append(LocationSQL.gsp_id)

    # filter on historic
    query = query.filter(ForecastSQL.historic == historic)

    # filter on target time
    if start_target_time is not None:
        query = filter_query_on_target_time(
            query=query,
            start_target_time=start_target_time,
            historic=historic,
            end_target_time=end_target_time,
        )

    query = query.join(LocationSQL)

    # option to preload values, makes querying quicker
    if preload_children:
        query = query.options(joinedload(ForecastSQL.location))
        query = query.options(joinedload(ForecastSQL.model))
        query = query.options(joinedload(ForecastSQL.input_data_last_updated))
        query = query.options(joinedload(ForecastSQL.forecast_values))

    order_by_cols.append(desc(ForecastSQL.created_utc))
    query = query.order_by(*order_by_cols)

    forecasts = query.all()

    logger.debug(f"Found {len(forecasts)} forecasts")
    if len(forecasts) > 0:
        logger.debug(f"The first forecast has {len(forecasts[0].forecast_values)} forecast_values")

    forecasts = sort_all_forecast_value(forecasts)

    return forecasts


def filter_query_on_target_time(
    query,
    historic: bool,
    start_target_time: Optional[datetime] = None,
    end_target_time: Optional[datetime] = None,
):
    """
    Filter query on start target time

    :param query: sql query
    :param start_target_time: datetime, target times only included after this
    :param historic: bool, if data is historic or latest
    :return: query
    """
    if historic:
        forecast_value_model = ForecastValueLatestSQL
        join_object = ForecastSQL.forecast_values_latest
    else:
        forecast_value_model = ForecastValueSQL
        join_object = ForecastSQL.forecast_values

    if (start_target_time is not None) or (end_target_time is not None):
        if start_target_time is not None:
            logger.debug(f"Filtering '{start_target_time=}'")
            query = query.join(join_object).filter(
                forecast_value_model.target_time >= start_target_time
            )
        if end_target_time is not None:
            logger.debug(f"Filtering '{end_target_time=}'")
            query = query.join(join_object).filter(
                forecast_value_model.target_time <= end_target_time
            )

        if historic:
            query = query.options(contains_eager(join_object)).populate_existing()

        query.order_by(join_object)

    return query


def get_forecast_values(
    session: Session,
    gsp_id: Optional[int] = None,
    start_datetime: Optional[datetime] = None,
    forecast_horizon_minutes: Optional[int] = None,
    only_return_latest: Optional[bool] = False,
    model: Optional = ForecastValueSQL,
) -> List[ForecastValueSQL]:
    """
    Get forecast values

    :param session: database session
    :param gsp_id: optional to gsp id, to filter query on
        If None is given then all are returned.
    :param start_datetime: optional to filterer target_time by start_datetime
        If None is given then all are returned.
    :param only_return_latest: Optional to only return the latest forecast, not all of them.
        Default is False
    :param forecast_horizon_minutes: Optional filter on forecast horizon. For example
        forecast_horizon_minutes=120, means load the forecast than was made 2 hours before the
        target time. Note this only works for non-historic data.
    :param model: Can be 'ForecastValueSQL' or 'ForecastValueSevenDaysSQL'

    return: List of forecasts values objects from database

    """

    # start main query
    assert model.__tablename__ in [
        ForecastValueSevenDaysSQL.__tablename__,
        ForecastValueSQL.__tablename__,
    ]
    query = session.query(model)

    if only_return_latest:
        query = query.distinct(model.target_time)

    if start_datetime is not None:
        query = query.filter(model.target_time >= start_datetime)

        # also filter on creation time, to speed up things
        created_utc_filter = start_datetime - timedelta(days=1)
        query = query.filter(model.created_utc >= created_utc_filter)
        query = query.filter(ForecastSQL.created_utc >= created_utc_filter)

    if forecast_horizon_minutes is not None:

        # this seems to only work for postgres
        query = query.filter(
            model.target_time - model.created_utc
            >= text(f"interval '{forecast_horizon_minutes} minute'")
        )
        query = query.filter(
            model.created_utc - datetime.now(tz=timezone.utc)
            <= text(f"interval '{forecast_horizon_minutes} minute'")
        )

    # filter on gsp_id
    if gsp_id is not None:
        query = query.join(ForecastSQL)
        query = query.join(LocationSQL)
        query = query.filter(LocationSQL.gsp_id == gsp_id)

    # order by target time and created time desc
    query = query.order_by(model.target_time, model.created_utc.desc())

    # get all results
    forecasts = query.all()

    return forecasts


def get_forecast_values_latest(
    session: Session,
    gsp_id: int,
    start_datetime: Optional[datetime] = None,
) -> List[ForecastValueLatestSQL]:
    """
    Get forecast values

    :param session: database session
    :param gsp_id: gsp id, to filter query on
    :param start_datetime: optional to filterer target_time by start_datetime
        If None is given then all are returned.

    return: List of forecasts values latest objects from database

    """

    # start main query
    query = session.query(ForecastValueLatestSQL)

    if start_datetime is not None:
        query = query.filter(ForecastValueLatestSQL.target_time >= start_datetime)

        # also filter on creation time, to speed up things
        created_utc_filter = start_datetime - timedelta(days=1)
        query = query.filter(ForecastValueLatestSQL.created_utc >= created_utc_filter)

    # filter on gsp_id
    if gsp_id is not None:
        query = query.filter(ForecastValueLatestSQL.gsp_id == gsp_id)

    # order by target time and created time desc
    query = query.order_by(ForecastValueLatestSQL.target_time)

    # get all results
    forecast_values_latest = query.all()

    return forecast_values_latest


def get_latest_national_forecast(
    session: Session,
) -> ForecastSQL:
    """
    Get forecast values

    :param session: database session
    :param gsp_id: optional to gsp id, to filter query on
        If None is given then all are returned.

    return: List of forecasts values objects from database

    """

    # start main query
    query = session.query(ForecastSQL)

    # filter on gsp_id
    query = query.join(LocationSQL)
    query = query.filter(LocationSQL.label == national_gb_label)

    # order, so latest is at the top
    query = query.order_by(ForecastSQL.created_utc.desc())

    # get first results
    forecast = query.first()

    return forecast


def get_latest_forecast_created_utc(session: Session, gsp_id: Optional[int] = None) -> datetime:
    """
    Get the latest forecast created utc value. Can choose for different gsps

    :param session: database session
    :param gsp_id: gsp id to filter query on
    :return:
    """

    # start main query
    query = session.query(ForecastSQL.created_utc)

    # filter on gsp_id
    if gsp_id is not None:
        query = query.join(LocationSQL)
        query = query.filter(LocationSQL.gsp_id == gsp_id)

    # order, so latest is at the top
    query = query.order_by(ForecastSQL.created_utc.desc())

    # get first results
    created_utc = query.first()

    assert len(created_utc) == 1

    return created_utc[0]


def get_location(
    session: Session,
    gsp_id: int,
    label: Optional[str] = None,
    installed_capacity_mw: Optional[int] = None,
) -> LocationSQL:
    """
    Get location object from gsp id

    :param session: database session
    :param gsp_id: gsp id of the location
    :param label: label of the location
    :param installed_capacity_mw: if a new location is created,
        this will be the installed capacity mw

    return: List of forecasts values objects from database

    """

    # start main query
    query = session.query(LocationSQL)

    # filter on gsp_id
    query = query.filter(LocationSQL.gsp_id == gsp_id)

    if label is not None:
        query = query.filter(LocationSQL.label == label)

    # get all results
    locations = query.all()

    if len(locations) == 0:
        logger.debug(f"Location for gsp_id {gsp_id} does not exist so going to add it")

        if label is None:
            label = f"GSP_{gsp_id}"

        location = LocationSQL(
            gsp_id=gsp_id, label=label, installed_capacity_mw=installed_capacity_mw
        )
        if gsp_id == 0:
            location.label = national_gb_label
        session.add(location)
        session.commit()

    else:
        location = locations[0]

    return location


def get_all_locations(session: Session, gsp_ids: List[int] = None) -> List[LocationSQL]:
    """
    Get all location object from gsp id

    :param session: database session
    :param gsp_ids: list of gsp id of the location

    return: List of GSP locations

    """

    # start main query
    query = session.query(LocationSQL)
    query = query.distinct(LocationSQL.gsp_id)

    get_national = True
    if gsp_ids is not None:
        # see if gsp_id==0 is in list
        # if gsp id 0 is in list, then get national gsp location
        # if gsp id 0 is not in list, then don't get national gsp location
        if 0 in gsp_ids:
            get_national = True
            gsp_ids.remove(0)
        else:
            get_national = False

        # filter on gsp_id
        query = query.filter(LocationSQL.gsp_id.in_(gsp_ids))
    else:
        query = query.filter(LocationSQL.gsp_id != 0)

    # make sure gsp is not null
    query = query.filter(LocationSQL.gsp_id.isnot(None))

    # query
    query = query.order_by(LocationSQL.gsp_id)

    # get all results
    locations = query.all()

    if get_national:
        nation = get_location(session=session, gsp_id=0, label=national_gb_label)
        locations = [nation] + locations

    return locations


def get_model(session: Session, name: str, version: str) -> MLModelSQL:
    """
    Get model object from name and version

    :param session: database session
    :param name: name of the model
    :param version: version of the model

    return: Model object

    """

    # start main query
    query = session.query(MLModelSQL)

    # filter on gsp_id
    query = query.filter(MLModelSQL.name == name)
    query = query.filter(MLModelSQL.version == version)

    # get all results
    models = query.all()

    if len(models) == 0:
        logger.debug(
            f"Model for name {name} and version {version }does not exist so going to add it"
        )

        model = MLModelSQL(name=name, version=version)
        session.add(model)
        session.commit()

    else:
        model = models[0]

    return model


def get_pv_system(
    session: Session, pv_system_id: int, provider: Optional[str] = "pvoutput.org"
) -> PVSystemSQL:
    """
    Get model object from name and version

    :param session: database session
    :param pv_system_id: pv system id
    :param provider: the pv provider, defaulted to pvoutput.org

    return: PVSystem object
    """

    # start main query
    query = session.query(PVSystemSQL)

    # filter on pv_system_id and provider
    query = query.filter(PVSystemSQL.pv_system_id == pv_system_id)
    query = query.filter(PVSystemSQL.provider == provider)

    # get all results
    pv_systems = query.all()

    pv_system = pv_systems[0]

    return pv_system
