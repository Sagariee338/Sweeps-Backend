from django.contrib.auth import authenticate, get_user_model, password_validation
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "display_name", "email_verified", "is_staff", "is_superuser", "created_at"]
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    display_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], display_name=attrs.get("display_name", ""))
        password_validation.validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(email=attrs["email"].lower().strip(), password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid email or password")
        if not user.email_verified:
            raise serializers.ValidationError("Verify your email address before signing in")
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect")
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value


class ProfileSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=80, allow_blank=True)


class VerifyTokenInput(serializers.Serializer):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=256)


class EmailInput(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordInput(VerifyTokenInput):
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})


class PauseInput(serializers.Serializer):
    days = serializers.ChoiceField(choices=[1, 7, 30])


class FundingLimitInput(serializers.Serializer):
    amount_cents = serializers.ChoiceField(choices=[1000, 2500, 5000, 10000], allow_null=True)
