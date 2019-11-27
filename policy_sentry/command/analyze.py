"""
    `analyze` will audit all locally downloaded IAM policy files and generate a report.

    Approach:
    * Policies should be downloaded entirely through the download-policies subcommand.
    * Compile list of actions, from the policy. This includes wildcards in the actions
    * Look them up in the database and expand them to all the explicit actions, to avoid bypass via s3:*
    * Generate a report to illustrate the risk levels of IAM policies across various accounts.
    * The risk levels are Credentials Exposure, Privilege Escalation, Network Exposure, and Resource Exposure.
"""
from glob import glob
import click
import os
from policy_sentry.shared.analyze import analyze_policy_directory
from policy_sentry.shared.database import connect_db
from policy_sentry.shared.report import load_report_config_file, create_csv_report, create_json_report, \
    create_markdown_report, create_markdown_report_template
from policy_sentry.shared.finding import Findings
from policy_sentry.shared.constants import HOME, CONFIG_DIRECTORY, DATABASE_FILE_PATH, \
    AUDIT_DIRECTORY_PATH

# Audit filenames
credentials_exposure_filename = AUDIT_DIRECTORY_PATH + '/credentials-exposure.txt'
data_access_filename = AUDIT_DIRECTORY_PATH + '/data-access-arn-list.txt'
privilege_escalation_filename = AUDIT_DIRECTORY_PATH + '/privilege-escalation.txt'
network_exposure_filename = AUDIT_DIRECTORY_PATH + '/network-exposure.txt'
resource_exposure_filename = AUDIT_DIRECTORY_PATH + '/resource-exposure.txt'
# data_access_arn_list_filename = AUDIT_DIRECTORY_PATH + '/data-access-arn-list.txt'


@click.command(
    short_help='Analyze all locally downloaded IAM policy files and generate a report.'
)
@click.option(
    '--report-config',
    default=HOME + CONFIG_DIRECTORY + 'report-config.yml',
    type=click.Path(exists=True),
    help='Custom report configuration file. Contains policy name exclusions and custom risk score weighting. '
         'Defaults to ~/.policy_sentry/report-config.yml'
)
@click.option(
    '--report-name',
    default='overall',
    type=str,
    help='Name of the report. Defaults to "overall".'
)
@click.option(
    '--include-markdown-report',
    default=False,
    is_flag=True,
    help='Use this flag to enable a Markdown report, which can be used with pandoc to generate an HTML report. '
         'Due to potentially very large report sizes, this is set to False by default.'
)
def analyze(report_config, report_name, include_markdown_report):
    """Analyze all locally downloaded IAM policy files and generate a report."""
    base_account_directories = glob(HOME + CONFIG_DIRECTORY + 'analysis/' + '*/')
    account_policy_directories = []

    for i in range(len(base_account_directories)):
        account_policy_directories.append(base_account_directories[i] + 'customer-managed/')
    db_session = connect_db(DATABASE_FILE_PATH)

    # Get report config
    report_config = load_report_config_file(report_config)
    excluded_role_patterns = report_config['report-config']['excluded-role-patterns']

    findings = Findings()

    print("Analyzing... ")
    for directory in base_account_directories:
        print(f"{directory}")
        account_id = os.path.split(os.path.dirname(directory))[-1]
        # Resource Exposure
        resource_exposure_findings = analyze_policy_directory(directory + 'customer-managed/', account_id,
                                                              db_session, resource_exposure_filename,
                                                              'resource_exposure', excluded_role_patterns)
        findings.add('resource_exposure', resource_exposure_findings)

        # Privilege Escalation
        privilege_escalation_findings = analyze_policy_directory(directory + 'customer-managed/', account_id,
                                                                 db_session, privilege_escalation_filename,
                                                                 'privilege_escalation', excluded_role_patterns)
        findings.add('privilege_escalation', privilege_escalation_findings)

        # Network Exposure
        network_exposure_findings = analyze_policy_directory(directory + 'customer-managed/', account_id,
                                                             db_session, network_exposure_filename,
                                                             'network_exposure', excluded_role_patterns)
        findings.add('network_exposure', network_exposure_findings)

        # Credentials exposure
        credentials_exposure_findings = analyze_policy_directory(directory + 'customer-managed/', account_id,
                                                                 db_session, credentials_exposure_filename,
                                                                 'credentials_exposure', excluded_role_patterns)
        findings.add('credentials_exposure', credentials_exposure_findings)

    occurrences = findings.get_findings()

    # Write JSON report
    json_report_path = create_json_report(occurrences, report_name)  # saved to `~/.policy_sentry/analysis/report_name.json`

    # Write Markdown formatted report, which can also be used for exporting to HTML with pandoc
    if include_markdown_report:
        report_contents = create_markdown_report_template(occurrences)
        # saved to `/.policy_sentry/analysis/report_name.md
        markdown_report_path = create_markdown_report(report_contents, report_name)

    # Write CSV report for overall results
    csv_report_path = create_csv_report(occurrences, report_name)  # saved to `/.policy_sentry/analysis/report_name.csv

    print(f"\nReports saved to: \n-{json_report_path}\n-{csv_report_path}\n\nThe JSON Report contains the raw data. "
          f"The CSV report shows a report summary.")
