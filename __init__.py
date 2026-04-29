from trytond.pool import Pool

from . import health_service
from . import product
from . import report
from . import wizard


def register():
    Pool.register(
        product.Product,
        health_service.HealthServiceLine,
        wizard.AppointmentCopagoV4Start,
        module='z_001_copago_services', type_='model')
    Pool.register(
        wizard.GenerateAppointmentCopagoV4,
        module='z_001_copago_services', type_='wizard')
    Pool.register(
        report.invoice.CopagoInvoiceReport,
        module='z_001_copago_services', type_='report')
