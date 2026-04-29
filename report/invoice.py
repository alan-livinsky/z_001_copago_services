import datetime
from types import SimpleNamespace

from trytond.pool import Pool
from trytond.report import Report
from trytond.transaction import Transaction


class CopagoInvoiceReport(Report):
    __name__ = 'z_001_copago_services.invoice'

    @classmethod
    def get_context(cls, records, header, data):
        context = super().get_context(records, header, data)
        format_number = context.get('format_number')
        format_currency = context.get('format_currency')

        def format_number_symbol(value, lang, symbol, digits=None):
            if format_number:
                try:
                    number = format_number(value, lang, digits=digits)
                except TypeError:
                    number = format_number(value, lang)
            else:
                number = str(value)

            symbol_text = (
                getattr(symbol, 'symbol', None)
                or getattr(symbol, 'name', None)
                or getattr(symbol, 'rec_name', None)
                or '')
            return ('%s %s' % (number, symbol_text)).strip()

        invoice = records[0] if records else None
        context['invoice'] = invoice
        context['tickets'] = [
            cls._get_ticket_context(record, format_currency)
            for record in records
        ]
        context['ticket'] = cls._get_ticket_context(invoice, format_currency)
        context['format_number_symbol'] = format_number_symbol
        return context

    @classmethod
    def _get_ticket_context(cls, invoice, format_currency):
        service_lines = cls._get_copago_service_lines(invoice)
        service = service_lines[0].name if service_lines else None
        appointment = cls._first(
            getattr(line, 'appointment', None) for line in service_lines)
        patient = (
            getattr(service, 'patient', None)
            or getattr(appointment, 'patient', None)
            or None)
        party = getattr(patient, 'name', None) or getattr(invoice, 'party', None)
        insurance = getattr(patient, 'current_insurance', None)

        def text(value):
            return value or ''

        def rec_name(record):
            return text(
                getattr(record, 'rec_name', None)
                or getattr(record, 'name', None))

        def party_document(party):
            alternative_ids = list(getattr(party, 'alternative_ids', []) or [])
            for alternative_id in alternative_ids:
                if getattr(alternative_id, 'alternative_id_type', None) in {
                        'country_id', 'medical_record', 'other'}:
                    return text(getattr(alternative_id, 'code', None))
            if alternative_ids:
                return text(getattr(alternative_ids[0], 'code', None))
            return text(getattr(party, 'ref', None))

        def medical_record(party):
            for alternative_id in getattr(party, 'alternative_ids', []) or []:
                if getattr(alternative_id, 'alternative_id_type', None) == \
                        'medical_record':
                    return text(getattr(alternative_id, 'code', None))
            return text(getattr(party, 'ref', None))

        def practice_code(line):
            product = getattr(line, 'product', None)
            template = getattr(product, 'template', None)
            return text(
                getattr(product, 'code', None)
                or getattr(template, 'code', None)
                or getattr(product, 'default_code', None))

        def line_amount(line):
            amount = getattr(line, 'amount', None)
            if format_currency and invoice:
                return format_currency(
                    amount, invoice.party.lang, invoice.currency)
            return text(amount)

        def format_date_value(value):
            if not value:
                return ''
            if hasattr(value, 'strftime'):
                return value.strftime('%d/%m/%Y')
            return text(value)

        ticket_lines = [
            SimpleNamespace(
                practice=practice_code(line),
                description=text(getattr(line, 'description', None)),
                amount=line_amount(line),
            )
            for line in getattr(invoice, 'lines', []) or []
            if getattr(line, 'type', None) == 'line'
        ]

        user = None
        try:
            user = Pool().get('res.user')(Transaction().user)
        except Exception:
            pass

        printed_at = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')
        total = ''
        if invoice:
            if format_currency:
                total = format_currency(
                    invoice.total_amount, invoice.party.lang, invoice.currency)
            else:
                total = text(getattr(invoice, 'total_amount', None))

        return SimpleNamespace(
            institution=rec_name(getattr(service, 'institution', None))
                or rec_name(getattr(invoice, 'company', None)),
            medical_program=rec_name(getattr(insurance, 'company', None)),
            plan=rec_name(getattr(insurance, 'plan_id', None))
                or rec_name(getattr(getattr(insurance, 'plan_id', None),
                    'name', None)),
            affiliate_number=text(getattr(insurance, 'number', None)),
            document_number=party_document(party),
            professional=rec_name(getattr(appointment, 'healthprof', None)),
            authorization='',
            observations=text(getattr(invoice, 'comment', None))
                or text(getattr(appointment, 'comments', None)),
            date=getattr(invoice, 'invoice_date', None) or datetime.date.today(),
            date_text=format_date_value(
                getattr(invoice, 'invoice_date', None) or datetime.date.today()),
            voucher_number=text(getattr(invoice, 'number', None))
                or text(getattr(invoice, 'id', None)),
            birth_date=getattr(party, 'dob', None),
            birth_date_text=format_date_value(getattr(party, 'dob', None)),
            medical_record=medical_record(party),
            patient=rec_name(patient) or rec_name(party),
            lines=ticket_lines,
            total=total,
            printed_at=printed_at,
            terminal=text(Transaction().context.get('terminal')),
            user=rec_name(user),
        )

    @staticmethod
    def _get_copago_service_lines(invoice):
        if not invoice:
            return []
        try:
            HealthServiceLine = Pool().get('gnuhealth.health_service.line')
            return HealthServiceLine.search([
                ('copago_invoice', '=', invoice.id),
            ])
        except Exception:
            return []

    @staticmethod
    def _first(values):
        for value in values:
            if value:
                return value
        return None
