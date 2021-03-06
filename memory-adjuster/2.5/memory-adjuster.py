#!/usr/bin/env python
from __future__ import print_function
import sys
import datetime
from os import sysconf
from optparse import OptionParser

# where to store components configs
DEFAULT_CONF_DIR = "/etc/zoomdata"

# Amount of Total memory used by OS, Metadata DB and other soft
DEFAULT_NON_PRODUCT_MEMORY_FRACT = 15

# EDC related defaults:
DEFAULT_EDC_SERVER_COUNT = 17
DEFAULT_EDC_XMS = 128
DEFAULT_EDC_XMX = 256

DEFAULT_MARKER = "# Autogenerated memory settings - do not edit manually!\n"

DEFAULT_INFO_STAMP_TEMPLATE = "# Total instance memory: {0}, Generation date: {1}\n"

HELP_MESSAGE = """%prog [options] allowed_mem

  Script to auto adjust memory settings for Zoomdata application and components.

  allowed_mem  - Amount of memory in Mb allowed to use by Zoomdata.
                 Total instance memory will be used by default.
"""

# Components description with memory limits
components = [
    {
        'name': 'scheduler',
        'mem_xmx_min': 512,
        'mem_xmx_fract': 0.01,
        'conf_file_name': 'scheduler.env'
    },
    {
        'name': 'spark-proxy',
        'mem_xmx_min': 1024,
        'mem_xmx_fract': 0.27,
        'conf_file_name': 'spark-proxy.env'
    },
    {
        'name': 'zoomdata',
        'mem_xmx_min': 4096,
        'mem_xmx_fract': 0.63,
        'conf_file_name': 'zoomdata.env'
    }
]


def get_total_memory():
    return int(sysconf('SC_PAGE_SIZE') * sysconf('SC_PHYS_PAGES') / (1024.0**2))


def parse_args():
    parser = OptionParser(usage=HELP_MESSAGE)
    parser.add_option("--config-dir", dest="config_dir",
                      default=DEFAULT_CONF_DIR, type="string",
                      help="Config dir to put <component>.env files. Default: {0}".format(DEFAULT_CONF_DIR)
                      )
    parser.add_option("--edcs-count", dest="edcs_count",
                      default=DEFAULT_EDC_SERVER_COUNT, type="int",
                      help="EDC servers count running on this host. Default: {0}".format(DEFAULT_EDC_SERVER_COUNT)
                      )
    parser.add_option("--os-reserved", dest="os_reserved",
                      default=DEFAULT_NON_PRODUCT_MEMORY_FRACT, type="int",
                      help="Percent of memory reserved for OS. Default: {0}%".format(DEFAULT_NON_PRODUCT_MEMORY_FRACT)
                      )
    return parser.parse_args()


def main():

    opts, args = parse_args()

    mem_total_instance = get_total_memory()

    if len(args) >= 1:
        mem_total = int(sys.argv[1])
    else:
        mem_total = mem_total_instance

    mem_reserved_pers = opts.os_reserved
    if mem_reserved_pers < 0 or mem_reserved_pers > 100:
        print("Error: os-reserved parameter ({0}) is out of bounds, will use default - {1}".
                  format(mem_reserved_pers, DEFAULT_NON_PRODUCT_MEMORY_FRACT))
        mem_reserved_pers = DEFAULT_NON_PRODUCT_MEMORY_FRACT

    # looking if os reservation is applicable here
    if mem_total > int(mem_total_instance * (1 - mem_reserved_pers / 100.0)):
        # reducing avail memory by reserved_mem percents
        mem_avail = int(mem_total * (1 - mem_reserved_pers / 100.0))
    else:
        mem_avail = mem_total

    # reducing avail memory by amount of EDC servers runnign on this host
    mem_avail = mem_avail - opts.edcs_count * DEFAULT_EDC_XMX

    mem_left = mem_avail

    print("Total memory: {0}Mb, Available for distribution: {1}Mb".format(mem_total, mem_avail))
    print("  OS reserved: {0}Mb, EDCs consumed: {1}Mb".format(
        int(mem_total * mem_reserved_pers / 100.0) if mem_total > int(mem_total_instance * (1 - mem_reserved_pers / 100.0)) else 0,
        opts.edcs_count * DEFAULT_EDC_XMX
    ))


    for c in components:
        mem_fract = int(mem_avail * c['mem_xmx_fract'])
        c['xmx'] = mem_fract if mem_fract > c['mem_xmx_min'] else c['mem_xmx_min']
        # check if avail memory is more then c['mem_xmx_min']
        c['xmx'] = c['xmx'] if mem_left >= c['mem_xmx_min'] else mem_left
        # assume Xms as 33% of Xmx
        c['xms'] = int(c['xmx'] * 0.33)
        mem_left -= c['xmx']
        print("Adjusting {0}, -Xms: {1}Mb, -Xmx: {2}Mb".format(c['name'], c['xms'], c['xmx']))

        # check if env config file is already exists and contains marker
        env_file_name = "{0}/{1}".format(opts.config_dir, c['conf_file_name'])
        try:
            if DEFAULT_MARKER.strip() in [line.strip() for line in open(env_file_name, "r").readlines()]:
                print("Previous adjustments was found for {0} component".format(c['name']))
                print("Remove all lines started with \"{0}\" in file {1}".format(DEFAULT_MARKER.strip(), env_file_name))
                print("and restart this script")
                continue
        except:
            print("Env config file for {0} doesn't exist - going to create it".format(c['name']))

        try:
            with open(env_file_name, "a+") as env_file:
                # generating generator comment in env file
                env_file.write(DEFAULT_MARKER)
                env_file.write(DEFAULT_INFO_STAMP_TEMPLATE.format(mem_total, str(datetime.date.today())))
                env_file.write("JAVA_OPTS=\"$JAVA_OPTS -Xms{xms}m -Xmx{xmx}m\"\n".format( xms=c['xms'], xmx=c['xmx']))
                env_file.flush()
                env_file.close()
        except IOError as e:
            print("Error! Unable to update {0} config file, status = {1}".format(env_file_name, e))


if __name__ == "__main__":
    main()
