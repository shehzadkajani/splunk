def enum(**named_values):
    return type('Enum', (), named_values)

Type = enum(SNAPSHOT='snapshot', CONTINUOUS='continuous')
