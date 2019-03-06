"""ADT proxy for ABAP Class (OO)"""

import sys
import sap.adt
import sap.cli.core


class CommandGroup(sap.cli.core.CommandGroup):
    """Adapter converting command line parameters to sap.adt.Class methods
       calls.
    """

    def __init__(self):
        super(CommandGroup, self).__init__('class')


@CommandGroup.command()
@CommandGroup.argument('--testclasses', default=False, action='store_true')
@CommandGroup.argument('name')
def read(connection, args):
    """Prints it out based on command line configuration.
    """

    cls = sap.adt.Class(connection, args.name)

    if args.testclasses:
        print(cls.test_classes.text)
    else:
        print(cls.text)


@CommandGroup.command()
@CommandGroup.argument('package')
@CommandGroup.argument('description')
@CommandGroup.argument('name')
def create(connection, args):
    """Creates the requested class"""

    metadata = sap.adt.ADTCoreData(language='EN', master_language='EN', responsible=connection.user.upper())
    clas = sap.adt.Class(connection, args.name.upper(), package=args.package.upper(), metadata=metadata)
    clas.description = args.description
    clas.create()


@CommandGroup.command()
@CommandGroup.argument('source', help='a path or - for stdin')
@CommandGroup.argument('--testclasses', default=False, action='store_true')
@CommandGroup.argument('name')
def write(connection, args):
    """Changes main source code of the given class"""

    text = None

    if args.source == '-':
        text = sys.stdin.readlines()
    else:
        with open(args.source) as filesrc:
            text = filesrc.readlines()

    clas = sap.adt.Class(connection, args.name.upper())
    # TODO: context manager
    clas.lock()
    try:
        if args.testclasses:
            clas.test_classes.change_text(''.join(text))
        else:
            clas.change_text(''.join(text))
    finally:
        clas.unlock()


@CommandGroup.command()
@CommandGroup.argument('name')
def activate(connection, args):
    """Actives the given class.
    """

    clas = sap.adt.Class(connection, args.name)
    clas.activate()
