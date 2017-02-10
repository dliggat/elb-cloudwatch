import boto3
import logging
import os
import datetime
import yaml

from my_lambda_package.utility import Utility


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

client = boto3.client('cloudwatch')

def _loadbalancer_response_count(metric, lbname, interval_seconds):
    """Counts the number of HTTP responses of the given type in interval_seconds.

    Args:
        metric: (str) Load balancer metric name, e.g. HTTPCode_Backend_2XX.
        interval_seconds: (int) The period in seconds to count the response codes.

    Returns:
        (float) The number of such HTTP responses over the interval.
    """
    statistic = 'Sum'
    response = client.get_metric_statistics(
        Namespace='AWS/ELB',
        MetricName=metric,
        Dimensions=[
            {
                'Name': 'LoadBalancerName',
                'Value': lbname
            }
        ],
        StartTime=datetime.datetime.utcnow() - datetime.timedelta(seconds=interval_seconds),
        EndTime=datetime.datetime.utcnow(),
        Period=interval_seconds,
        Statistics=[statistic],
        Unit='Count'
    )
    logger.info(response)
    result = 0.0
    for datapoint in response['Datapoints']:
        result += datapoint[statistic]
    logger.info('Returning {0} for metric {1}'.format(result, metric))
    return result


def _publish_metric(value, metric_name, namespace='Custom'):
    """Writes custom metrics to CloudWatch.

    Args:
        value: (float) Numeric value of the metric.
        metric_name: (str) A label for the custom metric.
        namespace: (str) A namespace to contain the custom metric.
    """
    if bool(os.getenv('MOCK')):
        logger.info('Mock detected; will not publish to CloudWatch')
    else:
        logger.info('Publishing to CloudWatch')
        client.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                  'MetricName': metric_name,
                  'Value': value
                }
            ]
        )

    logger.info('Put {0}:{1} metric value: {2}'.format(namespace, metric_name, value))


def _load_config(filename='config.yaml'):
    """Loads the configuration file."""
    with open(os.path.abspath(os.path.join(os.path.dirname(__file__), filename)), 'r') as f:
        config = yaml.load(f)
        logger.info('Loaded config: {0}'.format(config))
    return config


def handler(event, context):
    """Entry point for the Lambda function."""

    config = _load_config()

    http_200 = _loadbalancer_response_count('HTTPCode_Backend_2XX',
        lbname=config['load_balancer_name'], interval_seconds=config['interval_seconds'])
    http_500 = _loadbalancer_response_count('HTTPCode_Backend_5XX',
        lbname=config['load_balancer_name'], interval_seconds=config['interval_seconds'])

    numerator = http_200
    denominator = http_200 + http_500

    if denominator < 1:
        logger.info('Insufficient data for a new metric; will not publish.')
        return

    metric_value = numerator / denominator
    _publish_metric(metric_value,
        metric_name=config['metric_name'], namespace=config['custom_namespace'])


if __name__ == '__main__':
    from my_lambda_package.localcontext import LocalContext
    handler(None, LocalContext())
