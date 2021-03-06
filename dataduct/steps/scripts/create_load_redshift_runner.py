#!/usr/bin/env python

"""Replacement for the load step to use the redshift COPY command instead
"""

import argparse
import pandas.io.sql as pdsql
from dataduct.config import get_aws_credentials
from dataduct.data_access import redshift_connection
from dataduct.database import SqlStatement
from dataduct.database import Table
from dataduct.utils.helpers import stringify_credentials


def load_redshift(table, input_paths, max_error=0,
                  replace_invalid_char=None, no_escape=False, gzip=False,
                  command_options=None):
    """Load redshift table with the data in the input s3 paths
    """
    table_name = table.full_name
    print 'Loading data into %s' % table_name

    # Credentials string
    aws_key, aws_secret, token = get_aws_credentials()
    creds = stringify_credentials(aws_key, aws_secret, token)

    delete_statement = 'DELETE FROM %s;' % table_name
    error_string = 'MAXERROR %d' % max_error if max_error > 0 else ''
    if replace_invalid_char is not None:
        invalid_char_str = "ACCEPTINVCHARS AS %s" % replace_invalid_char
    else:
        invalid_char_str = ''

    query = [delete_statement]

    template = \
        "COPY {table} FROM '{path}' WITH CREDENTIALS AS '{creds}' {options};"

    for input_path in input_paths:
        if not command_options:
            command_options = (
                "DELIMITER '\t' {escape} {gzip} NULL AS 'NULL' TRUNCATECOLUMNS "
                "{max_error} {invalid_char_str};"
            ).format(escape='ESCAPE' if not no_escape else '',
                     gzip='GZIP' if gzip else '',
                     max_error=error_string,
                     invalid_char_str=invalid_char_str)

        statement = template.format(table=table_name,
                                    path=input_path,
                                    creds=creds,
                                    options=command_options)
        query.append(statement)

    return ' '.join(query)


def main():
    """Main Function
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--table_definition', dest='table_definition',
                        required=True)
    parser.add_argument('--max_error', dest='max_error', default=0, type=int)
    parser.add_argument('--replace_invalid_char', dest='replace_invalid_char',
                        default=None)
    parser.add_argument('--no_escape', action='store_true', default=False)
    parser.add_argument('--gzip', action='store_true', default=False)
    parser.add_argument('--command_options', dest='command_options', default=None)
    parser.add_argument('--s3_input_paths', dest='input_paths', nargs='+')
    args = parser.parse_args()
    print args

    table = Table(SqlStatement(args.table_definition))
    connection = redshift_connection()
    table_not_exists = pdsql.read_sql(table.check_not_exists_script().sql(),
                                      connection).loc[0][0]

    cursor = connection.cursor()
    # Create table in redshift, this is safe due to the if exists condition
    if table_not_exists:
        cursor.execute(table.create_script().sql())

    # Load data into redshift
    load_query = load_redshift(table, args.input_paths, args.max_error,
                               args.replace_invalid_char, args.no_escape,
                               args.gzip, args.command_options)
    cursor.execute(load_query)
    cursor.execute('COMMIT')
    cursor.close()
    connection.close()


if __name__ == '__main__':
    main()
