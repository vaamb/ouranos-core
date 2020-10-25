from dateutil.relativedelta import relativedelta


def human_delta_time(start, end):
    uptime = relativedelta(end, start)
    years = uptime.years
    months = uptime.months
    days = uptime.days
    hours = uptime.hours
    minutes = uptime.minutes
    seconds = uptime.seconds
    if years > 1:
        if months >= 6:
            return f"{years} years and a half"
        elif months < 6:
            return f"{years} years"
    elif years == 1:
        if months > 2:
            return f"{years} year and {months} months"
        elif months == 1:
            return f"{years} year and {months} month"
        else:
            return f"{years} year"
    else:
        if months > 1:
            if days > 1:
                return f'{months} months and {days} days'
            elif days == 1:
                return f'{months} months and {days} day'
            else:
                return f'{months} months'
        elif months == 1:
            if days > 1:
                return f'{months} month and {days} days'
            elif days == 1:
                return f'{months} month and {days} day'
            else:
                return f'{months} month'
        else:
            if days > 7:
                weeks = int(days/7)
                if weeks > 1:
                    return f"{weeks} weeks"
                if weeks == 1:
                    days_of_week = days % 7
                    if days_of_week > 1:
                        return f"{weeks} week and {days_of_week} days"
                    elif days_of_week == 1:
                        return f"{weeks} week and {days_of_week} day"
            elif days > 1:
                if hours > 1:
                    return f"{days} days and {hours} hours"
                elif hours == 1:
                    return f"{days} days and {hours} hour"
                else:
                    return f"{days} days"
            elif days == 1:
                if hours >= 1:
                    return f"{days} day and {hours} hours"
                elif hours == 1:
                    return f"{days} day and {hours} hour"
                else:
                    return f"{days} day"
            else:
                if hours > 1:
                    if minutes > 1:
                        return f"{hours} hours and {minutes} minutes"
                    elif minutes == 1:
                        return f"{hours} hours and {minutes} minute"
                    else:
                        return f"{hours} hours"
                elif hours == 1:
                    if minutes > 1:
                        return f"{hours} hour and {minutes} minutes"
                    if minutes == 1:
                        return f"{hours} hour and {minutes} minute"
                    else:
                        return f"{hours} hour"
                else:
                    if minutes >= 10:
                        return f"{minutes} minutes"
                    elif minutes > 1:
                        if seconds > 1:
                            return f"{minutes} minutes and {seconds} seconds"
                        elif seconds == 1:
                            return f"{minutes} minutes and {seconds} second"
                        else:
                            return f"{minutes} minutes"
                    elif minutes == 1:
                        if seconds > 1:
                            return f"{minutes} minute and {seconds} seconds"
                        elif seconds == 1:
                            return f"{minutes} minute and {seconds} second"
                        else:
                            return f"{minutes} minute"
                    else:
                        if seconds >= 15:
                            return f"{seconds} seconds"
                        else:
                            return "a few seconds"
