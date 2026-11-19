from django import forms


class BootstrapMixin:
    """Aplica as classes do Bootstrap 5 aos widgets de qualquer formulário."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                classe = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                classe = "form-select"
            else:
                classe = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {classe}".strip()
            if isinstance(widget, forms.DateInput):
                widget.input_type = "date"
                widget.format = "%Y-%m-%d"

    def full_clean(self):
        super().full_clean()
        for nome in self.errors:
            if nome in self.fields:
                attrs = self.fields[nome].widget.attrs
                attrs["class"] = f"{attrs.get('class', '')} is-invalid".strip()


class NomeUnicoNaCozinhaMixin:
    """Valida 'nome único por cozinha' mesmo quando o campo cozinha não está no formulário."""

    def clean_nome(self):
        nome = self.cleaned_data["nome"]
        cozinha_id = self.cleaned_data.get("cozinha") and self.cleaned_data["cozinha"].pk \
            or self.instance.cozinha_id
        repetido = type(self.instance).objects.filter(cozinha_id=cozinha_id, nome__iexact=nome) \
            .exclude(pk=self.instance.pk)
        if cozinha_id and repetido.exists():
            raise forms.ValidationError("Já existe um registro com esse nome nesta cozinha.")
        return nome
